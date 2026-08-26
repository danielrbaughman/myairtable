// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Typed record accessor for an Airtable table. Forwards all I/O to the {@link AirtableClient};
 * decodes responses into the generated {@code {Table}Model} classes via the supplied class token,
 * attaching the client + taking a snapshot on every decode so model-side {@code save()}/{@code
 * dirtyFields()} work.
 */
public final class OrmTable<T extends AirtableModel> {

  /** Airtable's hard cap for create / update / delete batches. */
  public static final int BATCH_SIZE = 10;

  /**
   * Max in-flight requests for the multi-ID {@link #get(List)} fan-out. Kept just under Airtable's
   * 5-requests-per-second limit so large ID lists don't trigger a synchronized 429 storm. Matches
   * {@link DictTable}.
   */
  public static final int MAX_CONCURRENT_GETS = 4;

  /** Result of {@link #upsert}: the merged model plus whether it was inserted. */
  public record UpsertResult<T>(T model, boolean wasCreated) {}

  private final String tableId;
  private final Class<T> modelType;
  private final AirtableClient client;

  public OrmTable(String tableId, Class<T> modelType, AirtableClient client) {
    this.tableId = tableId;
    this.modelType = modelType;
    this.client = client;
  }

  public String getTableId() {
    return tableId;
  }

  // ---- Decoding ----

  /**
   * Decode one {@code {id, createdTime, fields}} envelope: Jackson handles {@code fields};
   * id/createdTime are copied onto the model, the client attached, and a snapshot taken.
   */
  private T decodeEnvelope(JsonNode element) {
    try {
      JsonNode fields = element.path("fields");
      T model =
          AirtableJson.MAPPER.treeToValue(
              fields.isObject() ? fields : AirtableJson.MAPPER.createObjectNode(), modelType);
      model.setId(element.path("id").isTextual() ? element.path("id").asText() : null);
      model.setCreatedTime(
          element.path("createdTime").isTextual()
              ? AirtableDateParser.parse(element.path("createdTime").asText())
              : null);
      model.setAttachedClient(client);
      model.takeSnapshot();
      return model;
    } catch (AirtableException e) {
      throw e;
    } catch (Exception e) {
      throw new AirtableException.Decoding(e);
    }
  }

  private JsonNode parseTree(String payload) {
    try {
      return AirtableJson.MAPPER.readTree(payload);
    } catch (IOException e) {
      throw new AirtableException.Decoding(e);
    }
  }

  private T decodeRecordPayload(String payload) {
    return decodeEnvelope(parseTree(payload));
  }

  /** Decode a {@code {records: [...], offset}} payload. Returns models + offset. */
  private Map.Entry<List<T>, String> decodeListPayload(String payload) {
    JsonNode obj = parseTree(payload);
    List<T> records = new ArrayList<>();
    for (JsonNode record : obj.path("records")) {
      records.add(decodeEnvelope(record));
    }
    JsonNode offsetNode = obj.path("offset");
    String offset =
        offsetNode.isTextual() && !offsetNode.asText().isEmpty() ? offsetNode.asText() : null;
    return new AbstractMap.SimpleImmutableEntry<>(records, offset);
  }

  // ---- get (read) ----

  /** Fetch one record by ID. */
  public T get(String recordId) {
    return decodeRecordPayload(client.getRecord(tableId, recordId));
  }

  /**
   * Fetch many records by ID in windows of {@link #MAX_CONCURRENT_GETS}. Chunking bounds in-flight
   * requests (mirrors the Kotlin chunked-window design). Preserves caller-supplied order.
   */
  public List<T> get(List<String> recordIds) {
    if (recordIds.isEmpty()) {
      return List.of();
    }
    List<T> collected = new ArrayList<>(recordIds.size());
    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
      for (int start = 0; start < recordIds.size(); start += MAX_CONCURRENT_GETS) {
        List<String> window =
            recordIds.subList(start, Math.min(start + MAX_CONCURRENT_GETS, recordIds.size()));
        List<Callable<T>> tasks = window.stream().<Callable<T>>map(id -> () -> get(id)).toList();
        try {
          List<Future<T>> futures = executor.invokeAll(tasks);
          for (Future<T> future : futures) {
            collected.add(future.get());
          }
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          throw new AirtableException.Network(e);
        } catch (ExecutionException e) {
          if (e.getCause() instanceof AirtableException airtable) {
            throw airtable;
          }
          throw new AirtableException.Decoding(e.getCause());
        }
      }
    }
    return collected;
  }

  /** Fetch all records (default query). */
  public List<T> get() {
    return get(new AirtableQuery());
  }

  /**
   * Fetch records matching the query. Paginates internally via the {@code offset} continuation
   * token; returns the merged list in page-arrival order.
   */
  public List<T> get(AirtableQuery query) {
    List<T> collected = new ArrayList<>();
    String offset = null;
    do {
      String payload =
          offset != null ? fetchWithOffset(query, offset) : client.listRecords(tableId, query);
      Map.Entry<List<T>, String> page = decodeListPayload(payload);
      collected.addAll(page.getKey());
      offset = page.getValue();
    } while (offset != null);
    return collected;
  }

  private String fetchWithOffset(AirtableQuery query, String offset) {
    List<AirtableQuery.Param> params = new ArrayList<>(query.toParameters());
    params.add(new AirtableQuery.Param("offset", offset));
    return client.send("GET", client.tableUrl(tableId, params), null);
  }

  // ---- create ----

  /**
   * Create one record. Pass a fresh model built with its Builder (e.g. {@code
   * PrimaryModel.builder().primaryKey("x").build()}); only writable fields are sent.
   */
  public T create(T model) {
    return create(model, false);
  }

  /**
   * Create one record with optional {@code typecast}. When {@code typecast} is true Airtable
   * coerces string inputs to the cell's type (parsing dates/numbers, creating missing select
   * options).
   */
  public T create(T model, boolean typecast) {
    List<T> created = createBatch(List.of(model.toCreateFields()), typecast);
    if (created.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "create returned no records");
    }
    return created.get(0);
  }

  /**
   * Copy a record into a brand-new record.
   *
   * <p>Every writable field is copied verbatim, including the primary field. Computed fields are
   * omitted and recalculated by Airtable, so the copy gets its own id, autonumber and timestamps.
   * The source model is never modified.
   *
   * <p>Attachments are copied by URL, so Airtable re-ingests each file and the copy owns an
   * independent attachment rather than aliasing the source's.
   *
   * <p>Linked records are copied as-is. Airtable link fields are many-to-many underneath, so the
   * copy is added alongside the original on the far side of the link; the source record's own links
   * are never modified.
   */
  public T duplicate(T model) {
    return duplicate(model, false);
  }

  /** Copy a record, with optional {@code typecast}. */
  public T duplicate(T model, boolean typecast) {
    List<T> created =
        createBatch(
            List.of(AirtableJson.projectAttachmentsForCreate(model.toCreateFields())), typecast);
    if (created.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "duplicate returned no records");
    }
    return created.get(0);
  }

  /**
   * Read the record with {@code recordId} and copy it. Costs one extra GET, and in exchange the
   * copy reflects current server state and its attachment URLs are freshly signed (Airtable's
   * expire after roughly two hours).
   */
  public T duplicate(String recordId) {
    return duplicate(recordId, false);
  }

  /** Read the record with {@code recordId} and copy it, with optional {@code typecast}. */
  public T duplicate(String recordId, boolean typecast) {
    return duplicate(get(recordId), typecast);
  }

  /**
   * Copy many records into brand-new records. Chunks into Airtable's batch limit (10).
   *
   * <p>Named {@code duplicateModels} rather than an overload because {@code List<T>} and {@code
   * List<String>} erase to the same signature — the same reason {@code deleteModels} exists.
   */
  public List<T> duplicateModels(List<T> models) {
    return duplicateModels(models, false);
  }

  /** Copy many records, with optional {@code typecast}. */
  public List<T> duplicateModels(List<T> models, boolean typecast) {
    List<Map<String, JsonNode>> payloads =
        models.stream()
            .map(m -> AirtableJson.projectAttachmentsForCreate(m.toCreateFields()))
            .toList();
    List<T> collected = new ArrayList<>(models.size());
    for (int start = 0; start < payloads.size(); start += BATCH_SIZE) {
      collected.addAll(
          createBatch(
              payloads.subList(start, Math.min(start + BATCH_SIZE, payloads.size())), typecast));
    }
    return collected;
  }

  /** Read the records with {@code recordIds} and copy them, preserving the given order. */
  public List<T> duplicateAll(List<String> recordIds) {
    return duplicateAll(recordIds, false);
  }

  /** Read the records with {@code recordIds} and copy them, with optional {@code typecast}. */
  public List<T> duplicateAll(List<String> recordIds, boolean typecast) {
    if (recordIds.isEmpty()) {
      return List.of();
    }
    // get(List<String>) fans out on virtual threads but preserves caller order.
    return duplicateModels(get(recordIds), typecast);
  }

  /** Create many records. Chunks into Airtable's batch limit (10). */
  public List<T> create(List<T> models) {
    return create(models, false);
  }

  /**
   * Create many records with optional {@code typecast}. Chunks into Airtable's batch limit (10).
   */
  public List<T> create(List<T> models, boolean typecast) {
    List<Map<String, JsonNode>> payloads =
        models.stream().map(AirtableModel::toCreateFields).toList();
    List<T> collected = new ArrayList<>(models.size());
    for (int start = 0; start < payloads.size(); start += BATCH_SIZE) {
      collected.addAll(
          createBatch(
              payloads.subList(start, Math.min(start + BATCH_SIZE, payloads.size())), typecast));
    }
    return collected;
  }

  private List<T> createBatch(List<Map<String, JsonNode>> records, boolean typecast) {
    if (records.isEmpty()) {
      return List.of();
    }
    ObjectNode body = AirtableJson.MAPPER.createObjectNode();
    ArrayNode recordsNode = body.putArray("records");
    for (Map<String, JsonNode> fields : records) {
      ObjectNode fieldsNode = recordsNode.addObject().putObject("fields");
      fields.forEach(fieldsNode::set);
    }
    body.put("returnFieldsByFieldId", true);
    // Only emit `typecast` when opted in; Airtable's server-side default is false.
    if (typecast) {
      body.put("typecast", true);
    }
    String payload = client.createRecords(tableId, body.toString());
    return decodeListPayload(payload).getKey();
  }

  // ---- update ----

  /**
   * Update a single model. Diffs against the model's snapshot and sends only fields that changed
   * since the last {@code takeSnapshot()}.
   */
  public T update(T model) {
    return update(model, false);
  }

  /** Update a single model with optional {@code typecast}. */
  public T update(T model, boolean typecast) {
    List<T> updated = update(List.of(model), typecast);
    if (updated.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records");
    }
    return updated.get(0);
  }

  /**
   * Update many models (dirty fields only). Chunks into the batch limit. Models with no dirty
   * fields already match server state, so they are never PATCHed — they come back unchanged, in
   * their original positions.
   */
  public List<T> update(List<T> models) {
    return update(models, false);
  }

  /** Update many models (dirty fields only) with optional {@code typecast}. */
  public List<T> update(List<T> models, boolean typecast) {
    if (models.isEmpty()) {
      return List.of();
    }
    List<T> results = new ArrayList<>(java.util.Collections.nCopies(models.size(), (T) null));
    List<Integer> dirtyIndices = new ArrayList<>();
    List<Map.Entry<String, Map<String, JsonNode>>> dirtyPatches = new ArrayList<>();
    for (int index = 0; index < models.size(); index++) {
      T model = models.get(index);
      String recordId = model.getId();
      if (recordId == null || recordId.isEmpty()) {
        throw new AirtableException.Api("UNSAVED_MODEL", "Cannot update a model without an id");
      }
      Map<String, JsonNode> dirty = model.dirtyFields();
      if (dirty.isEmpty()) {
        results.set(index, model);
      } else {
        dirtyIndices.add(index);
        dirtyPatches.add(new AbstractMap.SimpleImmutableEntry<>(recordId, dirty));
      }
    }
    List<T> updated = new ArrayList<>();
    for (int start = 0; start < dirtyPatches.size(); start += BATCH_SIZE) {
      updated.addAll(
          updateBatch(
              dirtyPatches.subList(start, Math.min(start + BATCH_SIZE, dirtyPatches.size())),
              typecast));
    }
    for (int i = 0; i < dirtyIndices.size() && i < updated.size(); i++) {
      results.set(dirtyIndices.get(i), updated.get(i));
    }
    for (T result : results) {
      if (result == null) {
        throw new AirtableException.Api(
            "UNEXPECTED_RESPONSE", "update returned fewer records than requested");
      }
    }
    return results;
  }

  /** Update a record's fields directly by ID (no model required). */
  public T updateFields(String recordId, Map<String, JsonNode> fields) {
    return updateFields(recordId, fields, false);
  }

  /** Update a record's fields directly by ID with optional {@code typecast}. */
  public T updateFields(String recordId, Map<String, JsonNode> fields, boolean typecast) {
    List<T> updated =
        updateBatch(List.of(new AbstractMap.SimpleImmutableEntry<>(recordId, fields)), typecast);
    if (updated.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records");
    }
    return updated.get(0);
  }

  private List<T> updateBatch(
      List<Map.Entry<String, Map<String, JsonNode>>> patches, boolean typecast) {
    if (patches.isEmpty()) {
      return List.of();
    }
    ObjectNode body = AirtableJson.MAPPER.createObjectNode();
    ArrayNode recordsNode = body.putArray("records");
    for (Map.Entry<String, Map<String, JsonNode>> patch : patches) {
      ObjectNode record = recordsNode.addObject();
      record.put("id", patch.getKey());
      ObjectNode fieldsNode = record.putObject("fields");
      patch.getValue().forEach(fieldsNode::set);
    }
    body.put("returnFieldsByFieldId", true);
    if (typecast) {
      body.put("typecast", true);
    }
    String payload = client.updateRecords(tableId, body.toString());
    return decodeListPayload(payload).getKey();
  }

  // ---- upsert ----

  /**
   * Upsert a record, matching on the supplied field IDs. Returns the merged model plus whether the
   * record was inserted (vs updated).
   */
  public UpsertResult<T> upsert(T model, List<String> fieldsToMergeOn) {
    return upsert(model, fieldsToMergeOn, false);
  }

  /** Upsert a record with optional {@code typecast}. See {@link #upsert(AirtableModel, List)}. */
  public UpsertResult<T> upsert(T model, List<String> fieldsToMergeOn, boolean typecast) {
    ObjectNode body = AirtableJson.MAPPER.createObjectNode();
    ArrayNode recordsNode = body.putArray("records");
    ObjectNode fieldsNode = recordsNode.addObject().putObject("fields");
    model.toCreateFields().forEach(fieldsNode::set);
    ObjectNode performUpsert = body.putObject("performUpsert");
    ArrayNode mergeOn = performUpsert.putArray("fieldsToMergeOn");
    fieldsToMergeOn.forEach(mergeOn::add);
    body.put("returnFieldsByFieldId", true);
    if (typecast) {
      body.put("typecast", true);
    }

    // Idempotent only when a merge key is supplied: with fieldsToMergeOn the
    // request targets a stable identity (safe to retry on 5xx); without it the
    // upsert inserts, so a retry could duplicate (unified retry spec, kx1m).
    String payload = client.updateRecords(tableId, body.toString(), !fieldsToMergeOn.isEmpty());
    JsonNode obj = parseTree(payload);
    List<T> records = new ArrayList<>();
    for (JsonNode record : obj.path("records")) {
      records.add(decodeEnvelope(record));
    }
    if (records.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "upsert returned no records");
    }
    T first = records.get(0);
    boolean wasCreated = false;
    for (JsonNode createdId : obj.path("createdRecords")) {
      if (createdId.isTextual() && createdId.asText().equals(first.getId())) {
        wasCreated = true;
      }
    }
    return new UpsertResult<>(first, wasCreated);
  }

  // ---- delete ----

  /** Delete one record by ID. */
  public void delete(String recordId) {
    client.deleteRecord(tableId, recordId);
  }

  /** Delete the record referenced by this model's {@code id}. */
  public void delete(T model) {
    String id = model.getId();
    if (id == null || id.isEmpty()) {
      throw new AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model");
    }
    delete(id);
  }

  /**
   * Delete many records by ID. Chunks into Airtable's batch limit (10). (Named {@code deleteAll}
   * because Java's type erasure can't overload {@code delete(List<String>)} against {@code
   * delete(List<T>)} — the Kotlin target needed {@code @JvmName} for the same reason.)
   */
  public void deleteAll(List<String> recordIds) {
    for (int start = 0; start < recordIds.size(); start += BATCH_SIZE) {
      client.deleteRecords(
          tableId, recordIds.subList(start, Math.min(start + BATCH_SIZE, recordIds.size())));
    }
  }

  /** Delete many records by passing their models. Chunks by ID. */
  public void deleteModels(List<T> models) {
    List<String> ids = new ArrayList<>(models.size());
    for (T model : models) {
      String id = model.getId();
      if (id == null || id.isEmpty()) {
        throw new AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model");
      }
      ids.add(id);
    }
    deleteAll(ids);
  }
}
