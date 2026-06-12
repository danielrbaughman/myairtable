package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

// myairtable-acvg — bounded multi-ID get + empty-diff update partition.
//
// The Semaphore(4) bound itself is timing behavior and hard to unit test;
// what these tests pin is the observable contract that must survive the
// bounded fan-out: each ID's payload comes back in the slot it was requested
// in. The update tests pin the partition contract: models whose dirty diff
// is empty are never PATCHed and return as-is in their original positions.

/** Minimal hand-written model, mirroring what the generator emits. */
@Serializable
private class BoundedOpsStubModel(
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

private fun clientWith(engine: MockEngine): AirtableClient =
    AirtableClient(
        baseId = "appX",
        apiKey = "key",
        httpClient = HttpClient(engine),
    )

/** Engine that echoes the record ID from the request URL back as the payload. */
private fun echoEngine(): MockEngine =
    MockEngine { request ->
        val recordId = request.url.encodedPath.substringAfterLast('/')
        respond(
            content = """{"id": "$recordId", "fields": {"fldName": "name-$recordId"}}""",
            status = HttpStatusCode.OK,
            headers = headersOf(HttpHeaders.ContentType, "application/json"),
        )
    }

class TestTableMultiGetOrder {
    private val ids = (1..12).map { "rec%02d".format(it) }.shuffled(Random(7))

    @Test
    fun dictTableMultiGetPreservesCallerOrder() =
        runTest {
            val table = DictTable(tableId = "tblStub", client = clientWith(echoEngine()))
            val records = table.get(ids)
            assertEquals(ids, records.map { it.id })
        }

    @Test
    fun ormTableMultiGetPreservesCallerOrder() =
        runTest {
            val table = OrmTable(tableId = "tblStub", serializer = BoundedOpsStubModel.serializer(), client = clientWith(echoEngine()))
            val models = table.get(ids)
            assertEquals(ids, models.map { it.id })
            assertEquals(ids.map { "name-$it" }, models.map { it.name })
        }

    @Test
    fun multiGetEmptyInputMakesNoRequests() =
        runTest {
            val engine = echoEngine()
            val table = DictTable(tableId = "tblStub", client = clientWith(engine))
            assertEquals(emptyList(), table.get(emptyList<String>()))
            assertTrue(engine.requestHistory.isEmpty())
        }
}

class TestOrmTableUpdatePartition {
    /** A saved, snapshot-clean model: dirtyFields() is empty. */
    private fun cleanModel(recordId: String): BoundedOpsStubModel =
        BoundedOpsStubModel(name = "server-$recordId").apply {
            id = recordId
            takeSnapshot()
        }

    /** Engine that hard-fails any PATCH: proves clean models never hit the wire. */
    private fun patchRejectingEngine(): MockEngine =
        MockEngine { request ->
            if (request.method == HttpMethod.Patch) {
                respond(
                    content = """{"error": {"type": "SERVER_ERROR", "message": "PATCH must not happen"}}""",
                    status = HttpStatusCode.InternalServerError,
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
            } else {
                respond(
                    content = """{"records": []}""",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
            }
        }

    @Test
    fun allCleanModelsUpdateWithoutAnyRequest() =
        runTest {
            val engine = patchRejectingEngine()
            val table = OrmTable(tableId = "tblStub", serializer = BoundedOpsStubModel.serializer(), client = clientWith(engine))
            val models = listOf(cleanModel("rec01"), cleanModel("rec02"), cleanModel("rec03"))

            val results = table.update(models)

            assertTrue(engine.requestHistory.isEmpty(), "all-clean update must not issue any request")
            assertEquals(3, results.size)
            for ((index, model) in models.withIndex()) {
                assertSame(model, results[index], "clean models come back as the same instance, in position")
            }
        }

    @Test
    fun mixedListPatchesOnlyTheDirtyModelAndPreservesOrder() =
        runTest {
            val engine =
                MockEngine { request ->
                    respond(
                        content = """{"records": [{"id": "rec02", "fields": {"fldName": "renamed"}}]}""",
                        status = HttpStatusCode.OK,
                        headers = headersOf(HttpHeaders.ContentType, "application/json"),
                    )
                }
            val table = OrmTable(tableId = "tblStub", serializer = BoundedOpsStubModel.serializer(), client = clientWith(engine))

            val clean1 = cleanModel("rec01")
            val dirty = cleanModel("rec02").apply { name = "renamed" }
            val clean2 = cleanModel("rec03")

            val results = table.update(listOf(clean1, dirty, clean2))

            assertEquals(1, engine.requestHistory.size, "exactly one PATCH for the single dirty model")
            val request = engine.requestHistory.single()
            assertEquals(HttpMethod.Patch, request.method)
            val body = request.body.toByteArray().decodeToString()
            assertTrue("rec02" in body, "PATCH body must contain the dirty record id")
            assertFalse("rec01" in body, "clean record ids must not be PATCHed")
            assertFalse("rec03" in body, "clean record ids must not be PATCHed")

            assertEquals(3, results.size)
            assertSame(clean1, results[0])
            assertEquals("rec02", results[1].id)
            assertEquals("renamed", results[1].name)
            assertSame(clean2, results[2])
        }

    @Test
    fun singleCleanModelUpdateIsANoOp() =
        runTest {
            val engine = patchRejectingEngine()
            val table = OrmTable(tableId = "tblStub", serializer = BoundedOpsStubModel.serializer(), client = clientWith(engine))
            val model = cleanModel("rec01")

            val result = table.update(model)

            assertTrue(engine.requestHistory.isEmpty())
            assertSame(model, result)
        }
}
