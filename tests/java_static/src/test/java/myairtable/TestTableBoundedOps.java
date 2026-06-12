package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.net.http.HttpRequest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin myairtable-acvg (TestTableBoundedOps.kt) — bounded multi-ID get + empty-diff
 * update partition.
 *
 * <p>The chunked-window bound itself (MAX_CONCURRENT_GETS) is timing behavior and hard to unit
 * test; what these tests pin is the observable contract that must survive the bounded fan-out: each
 * ID's payload comes back in the slot it was requested in. The update tests pin the partition
 * contract: models whose dirty diff is empty are never PATCHed and return as-is in their original
 * positions.
 *
 * <p>Adaptation notes vs the Kotlin twin: Ktor's {@code MockEngine} becomes {@link FakeTransport}
 * (its request log mirrors {@code requestHistory}); the {@code @Serializable} stub model becomes a
 * Jackson POJO following the generated-model pattern; {@code OrmTable} takes a class token instead
 * of a serializer, and {@code DictTable} additionally takes its name-to-ID map (empty here).
 */
class TestTableBoundedOps {

  /** Minimal hand-written model, mirroring what the generator emits. */
  public static final class BoundedOpsStubModel implements AirtableModel {
    @JsonProperty("fldName")
    private String name;

    @JsonIgnore private String id;
    @JsonIgnore private Instant createdTime;
    @JsonIgnore private AirtableClient attachedClient;
    @JsonIgnore private Map<String, JsonNode> snapshot = Map.of();

    public BoundedOpsStubModel() {}

    public String getName() {
      return name;
    }

    public void setName(String name) {
      this.name = name;
    }

    @Override
    public String getTableId() {
      return "tblStub";
    }

    @Override
    public String getId() {
      return id;
    }

    @Override
    public void setId(String id) {
      this.id = id;
    }

    @Override
    public Instant getCreatedTime() {
      return createdTime;
    }

    @Override
    public void setCreatedTime(Instant createdTime) {
      this.createdTime = createdTime;
    }

    @Override
    public AirtableClient getAttachedClient() {
      return attachedClient;
    }

    @Override
    public void setAttachedClient(AirtableClient client) {
      this.attachedClient = client;
    }

    private Map<String, JsonNode> writableFields() {
      Map<String, JsonNode> fields = new LinkedHashMap<>();
      if (name != null) {
        fields.put("fldName", TextNode.valueOf(name));
      }
      return fields;
    }

    @Override
    public void takeSnapshot() {
      snapshot = writableFields();
    }

    @Override
    public Map<String, JsonNode> dirtyFields() {
      Map<String, JsonNode> current = writableFields();
      Map<String, JsonNode> dirty = new LinkedHashMap<>();
      for (Map.Entry<String, JsonNode> entry : current.entrySet()) {
        if (!entry.getValue().equals(snapshot.get(entry.getKey()))) {
          dirty.put(entry.getKey(), entry.getValue());
        }
      }
      for (String key : snapshot.keySet()) {
        if (!current.containsKey(key)) {
          dirty.put(key, NullNode.getInstance());
        }
      }
      return dirty;
    }

    @Override
    public Map<String, JsonNode> toRecord() {
      return writableFields();
    }

    @Override
    public Map<String, JsonNode> toCreateFields() {
      return writableFields();
    }
  }

  private static AirtableClient clientWith(FakeTransport transport) {
    return new AirtableClient(
        "appX",
        "key",
        "https://api.airtable.com/v0",
        new CacheStore(),
        3,
        0.01,
        0.05,
        30.0,
        transport);
  }

  /** Transport that echoes the record ID from the request URL back as the payload. */
  private static FakeTransport echoTransport() {
    return new FakeTransport(
        (request, callIndex) -> {
          String path = request.uri().getPath();
          String recordId = path.substring(path.lastIndexOf('/') + 1);
          return FakeTransport.Canned.ok(
              "{\"id\": \""
                  + recordId
                  + "\", \"fields\": {\"fldName\": \"name-"
                  + recordId
                  + "\"}}");
        });
  }

  private static List<String> shuffledIds() {
    List<String> ids = new ArrayList<>();
    for (int i = 1; i <= 12; i++) {
      ids.add(String.format("rec%02d", i));
    }
    Collections.shuffle(ids, new Random(7));
    return ids;
  }

  @Nested
  class TestTableMultiGetOrder {
    private final List<String> ids = shuffledIds();

    @Test
    void dictTableMultiGetPreservesCallerOrder() {
      DictTable table = new DictTable("tblStub", Map.of(), clientWith(echoTransport()));
      List<DictTable.Record> records = table.get(ids);
      assertEquals(ids, records.stream().map(DictTable.Record::id).toList());
    }

    @Test
    void ormTableMultiGetPreservesCallerOrder() {
      OrmTable<BoundedOpsStubModel> table =
          new OrmTable<>("tblStub", BoundedOpsStubModel.class, clientWith(echoTransport()));
      List<BoundedOpsStubModel> models = table.get(ids);
      assertEquals(ids, models.stream().map(BoundedOpsStubModel::getId).toList());
      assertEquals(
          ids.stream().map(id -> "name-" + id).toList(),
          models.stream().map(BoundedOpsStubModel::getName).toList());
    }

    @Test
    void multiGetEmptyInputMakesNoRequests() {
      FakeTransport transport = echoTransport();
      DictTable table = new DictTable("tblStub", Map.of(), clientWith(transport));
      List<String> empty = List.of();
      assertEquals(List.of(), table.get(empty));
      assertTrue(transport.requestHistory().isEmpty());
    }
  }

  @Nested
  class TestOrmTableUpdatePartition {
    /** A saved, snapshot-clean model: dirtyFields() is empty. */
    private BoundedOpsStubModel cleanModel(String recordId) {
      BoundedOpsStubModel model = new BoundedOpsStubModel();
      model.setName("server-" + recordId);
      model.setId(recordId);
      model.takeSnapshot();
      return model;
    }

    /** Transport that hard-fails any PATCH: proves clean models never hit the wire. */
    private FakeTransport patchRejectingTransport() {
      return new FakeTransport(
          (request, callIndex) -> {
            if ("PATCH".equals(request.method())) {
              return new FakeTransport.Canned(
                  500,
                  "{\"error\": {\"type\": \"SERVER_ERROR\", \"message\": \"PATCH must not"
                      + " happen\"}}",
                  FakeTransport.Canned.JSON_HEADERS);
            }
            return FakeTransport.Canned.ok("{\"records\": []}");
          });
    }

    @Test
    void allCleanModelsUpdateWithoutAnyRequest() {
      FakeTransport transport = patchRejectingTransport();
      OrmTable<BoundedOpsStubModel> table =
          new OrmTable<>("tblStub", BoundedOpsStubModel.class, clientWith(transport));
      List<BoundedOpsStubModel> models =
          List.of(cleanModel("rec01"), cleanModel("rec02"), cleanModel("rec03"));

      List<BoundedOpsStubModel> results = table.update(models);

      assertTrue(
          transport.requestHistory().isEmpty(), "all-clean update must not issue any request");
      assertEquals(3, results.size());
      for (int index = 0; index < models.size(); index++) {
        assertSame(
            models.get(index),
            results.get(index),
            "clean models come back as the same instance, in position");
      }
    }

    @Test
    void mixedListPatchesOnlyTheDirtyModelAndPreservesOrder() {
      FakeTransport transport =
          new FakeTransport(
              (request, callIndex) ->
                  FakeTransport.Canned.ok(
                      "{\"records\": [{\"id\": \"rec02\", \"fields\": {\"fldName\":"
                          + " \"renamed\"}}]}"));
      OrmTable<BoundedOpsStubModel> table =
          new OrmTable<>("tblStub", BoundedOpsStubModel.class, clientWith(transport));

      BoundedOpsStubModel clean1 = cleanModel("rec01");
      BoundedOpsStubModel dirty = cleanModel("rec02");
      dirty.setName("renamed");
      BoundedOpsStubModel clean2 = cleanModel("rec03");

      List<BoundedOpsStubModel> results = table.update(List.of(clean1, dirty, clean2));

      assertEquals(
          1, transport.requestHistory().size(), "exactly one PATCH for the single dirty model");
      HttpRequest request = transport.requestHistory().get(0);
      assertEquals("PATCH", request.method());
      String body = FakeTransport.bodyText(request);
      assertTrue(body.contains("rec02"), "PATCH body must contain the dirty record id");
      assertFalse(body.contains("rec01"), "clean record ids must not be PATCHed");
      assertFalse(body.contains("rec03"), "clean record ids must not be PATCHed");

      assertEquals(3, results.size());
      assertSame(clean1, results.get(0));
      assertEquals("rec02", results.get(1).getId());
      assertEquals("renamed", results.get(1).getName());
      assertSame(clean2, results.get(2));
    }

    @Test
    void singleCleanModelUpdateIsANoOp() {
      FakeTransport transport = patchRejectingTransport();
      OrmTable<BoundedOpsStubModel> table =
          new OrmTable<>("tblStub", BoundedOpsStubModel.class, clientWith(transport));
      BoundedOpsStubModel model = cleanModel("rec01");

      BoundedOpsStubModel result = table.update(model);

      assertTrue(transport.requestHistory().isEmpty());
      assertSame(model, result);
    }
  }
}
