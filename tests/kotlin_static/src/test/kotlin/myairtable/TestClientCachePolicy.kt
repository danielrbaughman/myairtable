package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * myairtable-p7eb — list-cache policy: multi-page payloads carry a
 * server-side `offset` continuation token that expires, so they must never
 * be cached; single-page payloads are.
 */
class TestClientCachePolicy {
    private fun clientReturning(body: String): AirtableClient {
        val engine =
            MockEngine {
                respond(
                    content = body,
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
            }
        return AirtableClient(
            baseId = "appX",
            apiKey = "key",
            cache = CacheStore(defaultTtlSeconds = 60.0),
            httpClient = HttpClient(engine),
        )
    }

    @Test
    fun singlePagePayloadIsCached() =
        runTest {
            val client = clientReturning("""{"records": []}""")
            client.listRecords("tbl1")
            assertEquals(1, client.cache.count())
        }

    @Test
    fun multiPagePayloadWithOffsetIsNotCached() =
        runTest {
            val client = clientReturning("""{"records": [], "offset": "itrAbc/recDef"}""")
            client.listRecords("tbl1")
            assertEquals(0, client.cache.count(), "payloads with a live offset token must not be cached")
        }

    @Test
    fun emptyStringOffsetCountsAsComplete() =
        runTest {
            val client = clientReturning("""{"records": [], "offset": ""}""")
            client.listRecords("tbl1")
            assertEquals(1, client.cache.count())
        }

    @Test
    fun getRecordCachingIsUnaffected() =
        runTest {
            val client = clientReturning("""{"id": "recX", "fields": {}}""")
            client.getRecord("tbl1", "recX")
            assertEquals(1, client.cache.count())
        }
}
