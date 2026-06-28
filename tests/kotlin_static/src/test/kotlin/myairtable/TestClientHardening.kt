package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.isActive
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * myairtable-jz87 — client hardening: Closeable ownership, retry-loop body
 * consumption, Retry-After cap / HTTP-date / jitter, transport-error
 * wrapping, and credential validation.
 *
 * Timing assertions use runTest's virtual clock ([currentTime]): `delay()`
 * inside the client is skipped instantly but still advances virtual time, so
 * waits are asserted exactly without real sleeps.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TestClientHardening {
    private val okBody = """{"records": []}"""

    /** MockEngine that answers 429 (with optional Retry-After) [failures] times, then 200. */
    private fun flakyEngine(
        failures: Int,
        retryAfter: String? = null,
        onCall: () -> Unit = {},
    ): MockEngine {
        var calls = 0
        return MockEngine {
            calls += 1
            onCall()
            if (calls <= failures) {
                respond(
                    content = """{"error": {"type": "RATE_LIMITED", "message": "slow down"}}""",
                    status = HttpStatusCode.TooManyRequests,
                    headers = if (retryAfter != null) headersOf(HttpHeaders.RetryAfter, retryAfter) else headersOf(),
                )
            } else {
                respond(
                    content = okBody,
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, "application/json"),
                )
            }
        }
    }

    // region Closeable ownership

    @Test
    fun closeDoesNotCloseInjectedClient() =
        runTest {
            val engine =
                MockEngine {
                    respond(
                        content = okBody,
                        status = HttpStatusCode.OK,
                        headers = headersOf(HttpHeaders.ContentType, "application/json"),
                    )
                }
            val injected = HttpClient(engine)
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = injected)
            client.listRecords("tbl1")
            client.close()
            assertTrue(injected.isActive, "injected client must survive AirtableClient.close()")
            assertTrue(engine.isActive, "injected engine must survive AirtableClient.close()")
            // The injected client is still fully usable after close().
            client.listRecords("tbl2")
            // The caller closes the injected client themselves — no exception.
            injected.close()
        }

    @Test
    fun closeClosesOwnedEngine() =
        runTest {
            // No injected client: the AirtableClient owns a real CIO engine.
            // apiBase points at a dead local port so a regression (engine left
            // open) fails fast as AirtableException.Network instead of hitting
            // the real API — a *closed* engine fails before any connection
            // attempt, with a non-Network error.
            val client = AirtableClient(baseId = "appX", apiKey = "key", apiBase = "http://127.0.0.1:9")
            client.close()
            client.close() // idempotent
            val result = runCatching { client.listRecords("tbl1") }
            assertTrue(result.isFailure, "request on a closed owned client must fail")
            assertFalse(
                result.exceptionOrNull() is AirtableException.Network,
                "failure must come from the closed engine, not a live connection attempt",
            )
        }

    // endregion

    // region Credential validation

    @Test
    fun blankApiKeyThrowsMissingCredentials() {
        assertFailsWith<AirtableException.MissingCredentials> {
            AirtableClient(baseId = "appX", apiKey = "")
        }
    }

    @Test
    fun blankBaseIdThrowsMissingCredentials() {
        assertFailsWith<AirtableException.MissingCredentials> {
            AirtableClient(baseId = "  ", apiKey = "key")
        }
    }

    // endregion

    // region Retry behavior

    @Test
    fun rateLimitedThenSuccessRetriesWithJitteredBackoff() =
        runTest {
            var calls = 0
            val engine = flakyEngine(failures = 1) { calls += 1 }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            val payload = client.listRecords("tbl1")
            assertEquals(okBody, payload)
            assertEquals(2, calls)
            // No Retry-After header: backoff = 0.5s * 2^0, jittered into [0.25s, 0.5s).
            assertTrue(currentTime in 250..500, "jittered backoff expected in [250ms, 500ms), got ${currentTime}ms")
        }

    @Test
    fun numericRetryAfterIsHonoredWithBoundedJitter() =
        runTest {
            val engine = flakyEngine(failures = 1, retryAfter = "0.05")
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            client.listRecords("tbl1")
            // Server-provided value is honored, plus a bounded decorrelation
            // jitter: wait = 0.05 + random*[0, min(0.05, RETRY_AFTER_JITTER_CAP)),
            // i.e. [50ms, 100ms). Jitter is present (spec: no path may be jitter-free)
            // but bounded so it stays a nudge, never a material delay.
            assertTrue(currentTime in 50..99, "Retry-After: 0.05 jittered into [50ms, 100ms), got ${currentTime}ms")
        }

    @Test
    fun absurdRetryAfterIsCappedAtMaxRetryDelay() =
        runTest {
            val engine = flakyEngine(failures = 1, retryAfter = "3600")
            val client =
                AirtableClient(
                    baseId = "appX",
                    apiKey = "key",
                    maxRetryDelaySeconds = 0.05,
                    httpClient = HttpClient(engine),
                )
            val payload = client.listRecords("tbl1")
            assertEquals(okBody, payload)
            assertEquals(50, currentTime, "Retry-After: 3600 must be capped to maxRetryDelaySeconds (50ms)")
        }

    @Test
    fun httpDateRetryAfterInThePastWaitsZero() =
        runTest {
            var calls = 0
            val engine = flakyEngine(failures = 1, retryAfter = "Wed, 21 Oct 2015 07:28:00 GMT") { calls += 1 }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            val payload = client.listRecords("tbl1")
            assertEquals(okBody, payload)
            assertEquals(2, calls)
            assertEquals(0, currentTime, "HTTP-date in the past must floor the wait at 0")
        }

    @Test
    fun terminal429ThrowsRateLimitedWithParsedRetryAfter() =
        runTest {
            val engine = flakyEngine(failures = 10, retryAfter = "0.01")
            val client =
                AirtableClient(
                    baseId = "appX",
                    apiKey = "key",
                    maxRetries = 1,
                    httpClient = HttpClient(engine),
                )
            val err =
                assertFailsWith<AirtableException.RateLimited> {
                    client.listRecords("tbl1")
                }
            assertEquals(0.01, err.retryAfterSeconds)
        }

    // endregion

    // region Network exception wrapping

    @Test
    fun transportIOExceptionSurfacesAsNetwork() =
        runTest {
            val engine = MockEngine { throw IOException("connection reset") }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            val err =
                assertFailsWith<AirtableException.Network> {
                    client.listRecords("tbl1")
                }
            assertTrue(err.cause is IOException)
            assertTrue(err.message!!.contains("connection reset"))
        }

    @Test
    fun networkIsCaughtByTheAirtableExceptionContract() =
        runTest {
            val engine = MockEngine { throw IOException("boom") }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            try {
                client.listRecords("tbl1")
                kotlin.test.fail("expected a throw")
            } catch (e: AirtableException) {
                assertTrue(e is AirtableException.Network)
            }
        }

    @Test
    fun networkEqualsSemanticsMatchSiblings() {
        assertEquals<AirtableException>(
            AirtableException.Network(IOException("a")),
            AirtableException.Network(IOException("b")),
        )
        assertFalse(AirtableException.Network(IOException("a")).equals(AirtableException.MissingCredentials()))
    }

    // endregion
}
