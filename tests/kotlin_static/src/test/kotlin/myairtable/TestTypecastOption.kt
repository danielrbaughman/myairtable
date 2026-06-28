package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

// myairtable-hbph — the per-request `typecast` option on create/update/upsert.
//
// Airtable's write API accepts a body-level `typecast` boolean; when true the
// server coerces string inputs to the cell's type. Default MUST be false and,
// matching the other targets, the key is OMITTED from the body when false
// (rather than emitted as `false`). These tests capture the outbound request
// body via Ktor's MockEngine (the runtime's real transport seam, same pattern
// as TestClientRetryPolicy / TestTableBoundedOps) and assert:
//   - typecast == true is present in the body when the caller opts in, and
//   - the `typecast` key is entirely absent by default.

/** Minimal hand-written model, mirroring what the generator emits. */
@Serializable
private class TypecastStubModel(
    @SerialName("fldName") var name: String? = null,
) : AirtableModel {
    @Transient
    override val tableId: String = "tblStub"

    @Transient
    override var id: RecordId? = null

    @Transient
    override var createdTime: Instant? = null

    @Transient
    override var attachedClient: AirtableClient? = null

    @Transient
    private var snapshot: Map<String, JsonElement> = emptyMap()

    private fun writableFields(): Map<String, JsonElement> = buildMap { name?.let { put("fldName", JsonPrimitive(it)) } }

    override fun takeSnapshot() {
        snapshot = writableFields()
    }

    override fun dirtyFields(): Map<String, JsonElement> {
        val current = writableFields()
        val dirty = mutableMapOf<String, JsonElement>()
        for ((key, value) in current) {
            if (snapshot[key] != value) dirty[key] = value
        }
        for (key in snapshot.keys) {
            if (key !in current) dirty[key] = JsonNull
        }
        return dirty
    }

    override fun toRecord(): Map<String, JsonElement> = writableFields()

    override fun toCreateFields(): Map<String, JsonElement> = writableFields()
}

class TestTypecastOption {
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    /**
     * Engine that records every outbound body and replays a canned write
     * response (records list, optionally with a createdRecords marker for
     * upsert). The first request's parsed JSON body is exposed for assertions.
     */
    private class CapturingEngine(
        responseBody: String,
    ) {
        val bodies = mutableListOf<JsonObject>()
        val engine =
            MockEngine { request ->
                val raw = request.body.toByteArray().decodeToString()
                bodies.add(AirtableJson.instance.parseToJsonElement(raw).jsonObject)
                respond(
                    content = responseBody,
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
            }

        fun firstBody(): JsonObject = bodies.first()
    }

    private fun clientWith(engine: MockEngine): AirtableClient = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))

    private val createResponse =
        """{"records": [{"id": "rec1", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {"fldName": "x"}}]}"""
    private val updateResponse =
        """{"records": [{"id": "rec1", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {"fldName": "y"}}]}"""
    private val upsertResponse =
        """{"records": [{"id": "rec1", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {"fldName": "z"}}], "createdRecords": ["rec1"]}"""

    private fun assertTypecastTrue(body: JsonObject) {
        val tc = body["typecast"]
        assertTrue(tc != null, "typecast key must be present when opted in")
        assertEquals(true, (tc as JsonPrimitive).booleanOrNull, "typecast must be the boolean true")
    }

    private fun assertTypecastAbsent(body: JsonObject) {
        assertFalse("typecast" in body, "typecast key must be omitted by default (not even emitted as false)")
    }

    // region OrmTable

    @Test
    fun ormCreateOmitsTypecastByDefault() =
        runTest {
            val cap = CapturingEngine(createResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            table.create(TypecastStubModel(name = "x"))
            assertTypecastAbsent(cap.firstBody())
        }

    @Test
    fun ormCreateEmitsTypecastWhenSet() =
        runTest {
            val cap = CapturingEngine(createResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            table.create(TypecastStubModel(name = "x"), typecast = true)
            assertTypecastTrue(cap.firstBody())
        }

    @Test
    fun ormUpdateOmitsTypecastByDefault() =
        runTest {
            val cap = CapturingEngine(updateResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            val model =
                TypecastStubModel(name = "x").apply {
                    id = "rec1"
                    takeSnapshot()
                }
            model.name = "y"
            table.update(model)
            assertTypecastAbsent(cap.firstBody())
        }

    @Test
    fun ormUpdateEmitsTypecastWhenSet() =
        runTest {
            val cap = CapturingEngine(updateResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            val model =
                TypecastStubModel(name = "x").apply {
                    id = "rec1"
                    takeSnapshot()
                }
            model.name = "y"
            table.update(model, typecast = true)
            assertTypecastTrue(cap.firstBody())
        }

    @Test
    fun ormUpsertOmitsTypecastByDefault() =
        runTest {
            val cap = CapturingEngine(upsertResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            table.upsert(TypecastStubModel(name = "z"), fieldsToMergeOn = listOf("fldName"))
            assertTypecastAbsent(cap.firstBody())
        }

    @Test
    fun ormUpsertEmitsTypecastWhenSet() =
        runTest {
            val cap = CapturingEngine(upsertResponse)
            val table = OrmTable(tableId = "tblStub", serializer = TypecastStubModel.serializer(), client = clientWith(cap.engine))
            table.upsert(TypecastStubModel(name = "z"), fieldsToMergeOn = listOf("fldName"), typecast = true)
            assertTypecastTrue(cap.firstBody())
        }

    // endregion

    // region DictTable

    @Test
    fun dictCreateOmitsTypecastByDefault() =
        runTest {
            val cap = CapturingEngine(createResponse)
            val table = DictTable(tableId = "tblStub", client = clientWith(cap.engine))
            table.create(Fields(mapOf("fldName" to JsonPrimitive("x"))))
            assertTypecastAbsent(cap.firstBody())
        }

    @Test
    fun dictCreateEmitsTypecastWhenSet() =
        runTest {
            val cap = CapturingEngine(createResponse)
            val table = DictTable(tableId = "tblStub", client = clientWith(cap.engine))
            table.create(Fields(mapOf("fldName" to JsonPrimitive("x"))), typecast = true)
            assertTypecastTrue(cap.firstBody())
        }

    @Test
    fun dictUpdateOmitsTypecastByDefault() =
        runTest {
            val cap = CapturingEngine(updateResponse)
            val table = DictTable(tableId = "tblStub", client = clientWith(cap.engine))
            table.update("rec1", Fields(mapOf("fldName" to JsonPrimitive("y"))))
            assertTypecastAbsent(cap.firstBody())
        }

    @Test
    fun dictUpdateEmitsTypecastWhenSet() =
        runTest {
            val cap = CapturingEngine(updateResponse)
            val table = DictTable(tableId = "tblStub", client = clientWith(cap.engine))
            table.update("rec1", Fields(mapOf("fldName" to JsonPrimitive("y"))), typecast = true)
            assertTypecastTrue(cap.firstBody())
        }

    // endregion
}
