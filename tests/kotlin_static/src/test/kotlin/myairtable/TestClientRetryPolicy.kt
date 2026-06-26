package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * myairtable-rxht T1 — deterministic / hermetic retry-policy test.
 *
 * The idempotency-aware retry policy lives in [AirtableClient.send]; its
 * `idempotent` flag drives whether 5xx is retried. This suite exercises the
 * policy end-to-end with NO network and NO real sleeping:
 *
 *  - Injection mechanism: the client accepts an injected Ktor [HttpClient]
 *    (constructor `httpClient` param; when null it builds its own CIO engine).
 *    We inject a [HttpClient] backed by Ktor's [MockEngine], which is the
 *    runtime's actual transport seam — the runtime is built on Ktor, not
 *    java.net.http. The MockEngine lambda scripts a sequence of canned
 *    responses and COUNTS how many times it is invoked (= attempts made).
 *  - No sleeping: a tiny [AirtableClient.baseRetryDelaySeconds] plus
 *    runTest's virtual clock means each backoff `delay()` resolves instantly.
 *
 * Policy under test:
 *  1. idempotent GET, 503,503,200      -> 3 attempts, success.
 *  2. idempotent op, persistent 503    -> maxRetries+1 attempts, then throws.
 *  3. non-idempotent createRecords 503 -> exactly 1 attempt, throws (no retry).
 *  4. 429 then 200                      -> retried (429 always retries).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TestClientRetryPolicy {
    private val okListBody = """{"records": []}"""
    private val okCreateBody = """{"records": [{"id": "rec1", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {}}]}"""
    private val serverErrorBody = """{"error": {"type": "INTERNAL_SERVER_ERROR", "message": "boom"}}"""
    private val rateLimitBody = """{"error": {"type": "RATE_LIMITED", "message": "slow down"}}"""

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    /**
     * MockEngine that replays [statuses] in order (one per attempt), returning
     * [okContent] on a 2xx and an error envelope otherwise. The shared [counter]
     * captures the number of transport invocations (= retry attempts). A short
     * [baseRetryDelaySeconds] keeps any real backoff negligible; runTest's
     * virtual clock skips it entirely.
     */
    private fun scriptedClient(
        statuses: List<HttpStatusCode>,
        okContent: String,
        retryAfter: String? = null,
        counter: IntArray,
    ): HttpClient {
        val engine =
            MockEngine { _ ->
                val idx = counter[0]
                counter[0] += 1
                // If the script runs out, keep returning the last status so an
                // over-retry shows up as extra attempts rather than an index crash.
                val status = statuses.getOrElse(idx) { statuses.last() }
                when {
                    status.value in 200..299 -> {
                        respond(content = okContent, status = status, headers = jsonHeaders)
                    }

                    status == HttpStatusCode.TooManyRequests -> {
                        respond(
                            content = rateLimitBody,
                            status = status,
                            headers = if (retryAfter != null) headersOf(HttpHeaders.RetryAfter, retryAfter) else headersOf(),
                        )
                    }

                    else -> {
                        respond(content = serverErrorBody, status = status, headers = jsonHeaders)
                    }
                }
            }
        return HttpClient(engine)
    }

    private fun client(
        http: HttpClient,
        maxRetries: Int = 3,
    ): AirtableClient =
        AirtableClient(
            baseId = "appX",
            apiKey = "key",
            maxRetries = maxRetries,
            // Tiny base delay so even the (virtual-clock-skipped) backoff is trivial.
            baseRetryDelaySeconds = 0.001,
            maxRetryDelaySeconds = 0.001,
            httpClient = http,
        )

    // 1. idempotent GET: 503, 503, 200 -> 3 attempts, success.
    @Test
    fun idempotentGetRetries503ThenSucceeds() =
        runTest {
            val attempts = intArrayOf(0)
            val http =
                scriptedClient(
                    statuses =
                        listOf(
                            HttpStatusCode.ServiceUnavailable,
                            HttpStatusCode.ServiceUnavailable,
                            HttpStatusCode.OK,
                        ),
                    okContent = okListBody,
                    counter = attempts,
                )
            val payload = client(http).listRecords("tbl1")
            assertEquals(okListBody, payload, "third attempt's 200 body must be returned")
            assertEquals(3, attempts[0], "two 503s then a 200 -> exactly 3 attempts")
        }

    // 2. idempotent op, persistent 503 -> maxRetries+1 attempts then throws.
    @Test
    fun idempotentGetPersistent503ExhaustsRetriesThenThrows() =
        runTest {
            val attempts = intArrayOf(0)
            val maxRetries = 3
            val http =
                scriptedClient(
                    statuses = List(10) { HttpStatusCode.ServiceUnavailable },
                    okContent = okListBody,
                    counter = attempts,
                )
            assertFailsWith<AirtableException> {
                client(http, maxRetries = maxRetries).listRecords("tbl1")
            }
            // Initial attempt + maxRetries retries = maxRetries + 1 total.
            assertEquals(maxRetries + 1, attempts[0], "persistent 503 -> maxRetries+1 attempts")
        }

    // 3. non-idempotent createRecords 503 -> exactly 1 attempt, throws (no retry).
    @Test
    fun nonIdempotentCreate503IsNotRetried() =
        runTest {
            val attempts = intArrayOf(0)
            val http =
                scriptedClient(
                    statuses = List(10) { HttpStatusCode.ServiceUnavailable },
                    okContent = okCreateBody,
                    counter = attempts,
                )
            assertFailsWith<AirtableException> {
                client(http).createRecords("tbl1", """{"records": [{"fields": {}}]}""")
            }
            assertEquals(1, attempts[0], "a non-idempotent POST must NOT be retried on 5xx")
        }

    // 4. 429 then 200 -> retried (429 always retries, even ignoring idempotency).
    @Test
    fun rateLimited429ThenSucceedsIsRetried() =
        runTest {
            val attempts = intArrayOf(0)
            val http =
                scriptedClient(
                    statuses = listOf(HttpStatusCode.TooManyRequests, HttpStatusCode.OK),
                    okContent = okListBody,
                    retryAfter = "0.001",
                    counter = attempts,
                )
            val payload = client(http).listRecords("tbl1")
            assertEquals(okListBody, payload)
            assertEquals(2, attempts[0], "429 then 200 -> exactly 2 attempts")
        }

    // Companion to #4: a non-idempotent create is STILL retried on 429, because
    // a 429 means the server rejected the request without applying it. This
    // pins the "429 always retries regardless of idempotency" half of the rule.
    @Test
    fun rateLimited429IsRetriedEvenForNonIdempotentCreate() =
        runTest {
            val attempts = intArrayOf(0)
            val http =
                scriptedClient(
                    statuses = listOf(HttpStatusCode.TooManyRequests, HttpStatusCode.OK),
                    okContent = okCreateBody,
                    retryAfter = "0.001",
                    counter = attempts,
                )
            val payload = client(http).createRecords("tbl1", """{"records": [{"fields": {}}]}""")
            assertEquals(okCreateBody, payload)
            assertEquals(2, attempts[0], "429 retries even a non-idempotent create -> 2 attempts")
        }
}
