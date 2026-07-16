// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Raw-dict record accessor for an Airtable table. Forwards all I/O to the {@link AirtableClient}.
 * Values flow through as {@link Fields} (dual ID/name-keyed {@code Map<String, JsonNode>}),
 * bypassing typed {@code {Table}Model} decoding.
 *
 * <p>Paired with {@code OrmTable<T>} (J-F4) — both share the same underlying client. Generated
 * {@code {Table}Table.dict()} exposes this accessor.
 */
public final class DictTable {

  /** Airtable's hard cap for create / update / delete batches. */
  public static final int BATCH_SIZE = 10;

  /**
   * Max in-flight requests for the multi-ID {@link #get(List)} fan-out. Kept just under Airtable's
   * 5-requests-per-second limit so large ID lists don't trigger a synchronized 429 storm.
   */
  public static final int MAX_CONCURRENT_GETS = 4;

  /** A fully-loaded record: id + createdTime + {@link Fields}. */
  public record Record(String id, Instant createdTime, Fields fields) {}

  // ---- Wire envelopes ----

  record RawRecordEnvelope(
      @JsonProperty("id") String id,
      @JsonProperty("createdTime") Instant createdTime,
      @JsonProperty("fields") Map<String, JsonNode> fields) {}

  record RawListResponse(
      @JsonProperty("records") List<RawRecordEnvelope> records,
      @JsonProperty("offset") String offset) {}

  /** A single update: record ID + the fields to patch. */
  public record Update(String id, Fields fields) {}

  private final String tableId;
  private final Map<String, String> nameToId;
  private final AirtableClient client;

  public DictTable(String tableId, Map<String, String> nameToId, AirtableClient client) {
    this.tableId = tableId;
    this.nameToId = nameToId;
    this.client = client;
  }

  public String getTableId() {
    return tableId;
  }

  private Record toRecord(RawRecordEnvelope raw) {
    Fields fields = new Fields(raw.fields() == null ? Map.of() : raw.fields(), nameToId);
    return new Record(raw.id(), raw.createdTime(), fields);
  }

  private static <T> T decode(String payload, Class<T> type) {
    try {
      return AirtableJson.MAPPER.readValue(payload, type);
    } catch (AirtableException e) {
      throw e;
    } catch (Exception e) {
      throw new AirtableException.Decoding(e);
    }
  }

  // ---- get (read) ----

  /** Fetch one record by ID. */
  public Record get(String recordId) {
    String payload = client.getRecord(tableId, recordId);
    return toRecord(decode(payload, RawRecordEnvelope.class));
  }

  /**
   * Fetch many records by ID in windows of {@link #MAX_CONCURRENT_GETS}. Chunking bounds in-flight
   * requests (mirrors the Kotlin chunked-window design). Preserves caller-supplied order.
   */
  public List<Record> get(List<String> recordIds) {
    if (recordIds.isEmpty()) {
      return List.of();
    }
    List<Record> collected = new ArrayList<>(recordIds.size());
    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
      for (int start = 0; start < recordIds.size(); start += MAX_CONCURRENT_GETS) {
        List<String> window =
            recordIds.subList(start, Math.min(start + MAX_CONCURRENT_GETS, recordIds.size()));
        List<Callable<Record>> tasks =
            window.stream().<Callable<Record>>map(id -> () -> get(id)).toList();
        try {
          List<Future<Record>> futures = executor.invokeAll(tasks);
          for (Future<Record> future : futures) {
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
  public List<Record> get() {
    return get(new AirtableQuery());
  }

  /**
   * Fetch records matching the query. Paginates internally using Airtable's {@code offset} token;
   * returns the full merged list.
   */
  public List<Record> get(AirtableQuery query) {
    List<Record> collected = new ArrayList<>();
    String offset = null;
    do {
      String payload =
          offset != null ? fetchWithOffset(query, offset) : client.listRecords(tableId, query);
      RawListResponse envelope = decode(payload, RawListResponse.class);
      if (envelope.records() != null) {
        for (RawRecordEnvelope raw : envelope.records()) {
          collected.add(toRecord(raw));
        }
      }
      offset = envelope.offset() != null && !envelope.offset().isEmpty() ? envelope.offset() : null;
    } while (offset != null);
    return collected;
  }

  /**
   * Refetch with an {@code offset} continuation token appended to the query parameters. {@link
   * AirtableQuery} intentionally doesn't model offset (it's a server-driven continuation, not a
   * user-facing parameter), so it is spliced in at the URL layer.
   */
  private String fetchWithOffset(AirtableQuery query, String offset) {
    List<AirtableQuery.Param> params = new ArrayList<>(query.toParameters());
    params.add(new AirtableQuery.Param("offset", offset));
    return client.send("GET", client.tableUrl(tableId, params), null);
  }

  // ---- create ----

  /** Create one record and return the populated envelope. */
  public Record create(Fields fields) {
    return create(fields, false);
  }

  /**
   * Create one record with optional {@code typecast}. When {@code typecast} is true Airtable
   * coerces string inputs to the cell's type (parsing dates/numbers, creating missing select
   * options).
   */
  public Record create(Fields fields, boolean typecast) {
    List<Record> created = createBatch(List.of(fields), typecast);
    if (created.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "create returned no records");
    }
    return created.get(0);
  }

  /** Create many records. Chunks into Airtable's 10-per-call batch limit. */
  public List<Record> create(List<Fields> fields) {
    return create(fields, false);
  }

  /** Create many records with optional {@code typecast}. Chunks into Airtable's batch limit. */
  public List<Record> create(List<Fields> fields, boolean typecast) {
    List<Record> collected = new ArrayList<>(fields.size());
    for (int start = 0; start < fields.size(); start += BATCH_SIZE) {
      collected.addAll(
          createBatch(
              fields.subList(start, Math.min(start + BATCH_SIZE, fields.size())), typecast));
    }
    return collected;
  }

  private List<Record> createBatch(List<Fields> fields, boolean typecast) {
    if (fields.isEmpty()) {
      return List.of();
    }
    ObjectNode body = AirtableJson.MAPPER.createObjectNode();
    ArrayNode records = body.putArray("records");
    for (Fields f : fields) {
      ObjectNode record = records.addObject();
      ObjectNode fieldsNode = record.putObject("fields");
      f.toMap().forEach(fieldsNode::set);
    }
    // Airtable echoes the inserted records back keyed by field ID, matching
    // `returnFieldsByFieldId=true` on list/get requests.
    body.put("returnFieldsByFieldId", true);
    // Only emit `typecast` when opted in; Airtable's server-side default is false.
    if (typecast) {
      body.put("typecast", true);
    }
    String payload = client.createRecords(tableId, body.toString());
    RawListResponse envelope = decode(payload, RawListResponse.class);
    List<Record> created = new ArrayList<>();
    if (envelope.records() != null) {
      for (RawRecordEnvelope raw : envelope.records()) {
        created.add(toRecord(raw));
      }
    }
    return created;
  }

  // ---- update ----

  /** Update a single record's field values. */
  public Record update(String recordId, Fields fields) {
    return update(recordId, fields, false);
  }

  /** Update a single record's field values with optional {@code typecast}. */
  public Record update(String recordId, Fields fields, boolean typecast) {
    List<Record> updated = updateBatch(List.of(new Update(recordId, fields)), typecast);
    if (updated.isEmpty()) {
      throw new AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records");
    }
    return updated.get(0);
  }

  /** Update many records. Chunks into Airtable's 10-per-call batch limit. */
  public List<Record> update(List<Update> updates) {
    return update(updates, false);
  }

  /** Update many records with optional {@code typecast}. Chunks into Airtable's batch limit. */
  public List<Record> update(List<Update> updates, boolean typecast) {
    List<Record> collected = new ArrayList<>(updates.size());
    for (int start = 0; start < updates.size(); start += BATCH_SIZE) {
      collected.addAll(
          updateBatch(
              updates.subList(start, Math.min(start + BATCH_SIZE, updates.size())), typecast));
    }
    return collected;
  }

  private List<Record> updateBatch(List<Update> updates, boolean typecast) {
    if (updates.isEmpty()) {
      return List.of();
    }
    ObjectNode body = AirtableJson.MAPPER.createObjectNode();
    ArrayNode records = body.putArray("records");
    for (Update update : updates) {
      ObjectNode record = records.addObject();
      record.put("id", update.id());
      ObjectNode fieldsNode = record.putObject("fields");
      update.fields().toMap().forEach(fieldsNode::set);
    }
    body.put("returnFieldsByFieldId", true);
    if (typecast) {
      body.put("typecast", true);
    }
    String payload = client.updateRecords(tableId, body.toString());
    RawListResponse envelope = decode(payload, RawListResponse.class);
    List<Record> updated = new ArrayList<>();
    if (envelope.records() != null) {
      for (RawRecordEnvelope raw : envelope.records()) {
        updated.add(toRecord(raw));
      }
    }
    return updated;
  }

  // ---- delete ----

  /** Delete one record by ID. */
  public void delete(String recordId) {
    client.deleteRecord(tableId, recordId);
  }

  /** Delete many records. Chunks into Airtable's 10-per-call batch limit. */
  public void delete(List<String> recordIds) {
    for (int start = 0; start < recordIds.size(); start += BATCH_SIZE) {
      client.deleteRecords(
          tableId, recordIds.subList(start, Math.min(start + BATCH_SIZE, recordIds.size())));
    }
  }
}
