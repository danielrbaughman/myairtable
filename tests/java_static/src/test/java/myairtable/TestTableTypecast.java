package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.node.TextNode;
import java.net.http.HttpRequest;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Hermetic verification of the per-request {@code typecast} option (myairtable-hbph) for the Java
 * create/update/upsert paths on both {@link OrmTable} and {@link DictTable}.
 *
 * <p>The contract: {@code typecast} is sent in the JSON request body as {@code "typecast": true}
 * ONLY when the caller opts in via the {@code boolean typecast} overload; the default overloads
 * must omit the key entirely (Airtable's server-side default is false, so existing behavior is
 * unchanged). A {@link FakeTransport} captures the POST/PATCH body for inspection — no socket
 * opens.
 */
class TestTableTypecast {

  /** A create/update echo response: one record back so the public methods don't throw. */
  private static final String OK_ONE_RECORD = "{\"records\": [{\"id\": \"recX\", \"fields\": {}}]}";

  private static AirtableClient clientWith(FakeTransport transport) {
    return new AirtableClient(
        "appX",
        "key",
        "https://api.airtable.com/v0",
        new CacheStore(),
        3,
        0.0,
        0.0,
        30.0,
        transport);
  }

  /** A transport that always echoes one record and records every request. */
  private static FakeTransport echoOne() {
    return new FakeTransport((request, callIndex) -> FakeTransport.Canned.ok(OK_ONE_RECORD));
  }

  /** The first request's body, as text. */
  private static String firstBody(FakeTransport transport) {
    assertEquals(1, transport.requestHistory().size(), "expected exactly one request");
    HttpRequest request = transport.requestHistory().get(0);
    return FakeTransport.bodyText(request);
  }

  private static Fields oneField() {
    return new Fields(Map.of("fldName", TextNode.valueOf("value")));
  }

  private static TestTableBoundedOps.BoundedOpsStubModel newModel(String name) {
    TestTableBoundedOps.BoundedOpsStubModel model = new TestTableBoundedOps.BoundedOpsStubModel();
    model.setName(name);
    return model;
  }

  /** A saved, dirty model: has an id and a changed field, so it will be PATCHed. */
  private static TestTableBoundedOps.BoundedOpsStubModel dirtyModel(String id) {
    TestTableBoundedOps.BoundedOpsStubModel model = newModel("before");
    model.setId(id);
    model.takeSnapshot();
    model.setName("after");
    return model;
  }

  // ---- OrmTable.create ----

  @Test
  void ormCreateOmitsTypecastByDefault() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.create(newModel("a"));

    assertFalse(firstBody(transport).contains("typecast"), "default create must omit typecast");
  }

  @Test
  void ormCreateSendsTypecastWhenSet() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.create(newModel("a"), true);

    assertTrue(
        firstBody(transport).contains("\"typecast\":true"), "opted-in create must send typecast");
  }

  // ---- OrmTable.update ----

  @Test
  void ormUpdateOmitsTypecastByDefault() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.update(dirtyModel("recX"));

    assertFalse(firstBody(transport).contains("typecast"), "default update must omit typecast");
  }

  @Test
  void ormUpdateSendsTypecastWhenSet() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.update(dirtyModel("recX"), true);

    assertTrue(
        firstBody(transport).contains("\"typecast\":true"), "opted-in update must send typecast");
  }

  // ---- OrmTable.upsert ----

  @Test
  void ormUpsertOmitsTypecastByDefault() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.upsert(newModel("a"), List.of("fldName"));

    assertFalse(firstBody(transport).contains("typecast"), "default upsert must omit typecast");
  }

  @Test
  void ormUpsertSendsTypecastWhenSet() {
    FakeTransport transport = echoOne();
    OrmTable<TestTableBoundedOps.BoundedOpsStubModel> table =
        new OrmTable<>(
            "tblStub", TestTableBoundedOps.BoundedOpsStubModel.class, clientWith(transport));

    table.upsert(newModel("a"), List.of("fldName"), true);

    assertTrue(
        firstBody(transport).contains("\"typecast\":true"), "opted-in upsert must send typecast");
  }

  // ---- DictTable.create ----

  @Test
  void dictCreateOmitsTypecastByDefault() {
    FakeTransport transport = echoOne();
    DictTable table = new DictTable("tblStub", Map.of(), clientWith(transport));

    table.create(oneField());

    assertFalse(firstBody(transport).contains("typecast"), "default create must omit typecast");
  }

  @Test
  void dictCreateSendsTypecastWhenSet() {
    FakeTransport transport = echoOne();
    DictTable table = new DictTable("tblStub", Map.of(), clientWith(transport));

    table.create(oneField(), true);

    assertTrue(
        firstBody(transport).contains("\"typecast\":true"), "opted-in create must send typecast");
  }

  // ---- DictTable.update ----

  @Test
  void dictUpdateOmitsTypecastByDefault() {
    FakeTransport transport = echoOne();
    DictTable table = new DictTable("tblStub", Map.of(), clientWith(transport));

    table.update("recX", oneField());

    assertFalse(firstBody(transport).contains("typecast"), "default update must omit typecast");
  }

  @Test
  void dictUpdateSendsTypecastWhenSet() {
    FakeTransport transport = echoOne();
    DictTable table = new DictTable("tblStub", Map.of(), clientWith(transport));

    table.update("recX", oneField(), true);

    assertTrue(
        firstBody(transport).contains("\"typecast\":true"), "opted-in update must send typecast");
  }
}
