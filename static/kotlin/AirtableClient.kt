// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.header
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.URLBuilder
import io.ktor.http.Url
import io.ktor.http.appendPathSegments
import io.ktor.http.contentType
import io.ktor.http.encodeURLParameter
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.serialization.Serializable
import java.io.Closeable
import java.io.IOException
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.random.Random
import kotlin.time.Duration.Companion.seconds

/**
 * HTTP client for the Airtable REST API, built on Ktor's coroutine-native
 * [HttpClient]. All network I/O flows through this class; [OrmTable] /
 * [DictTable] are thin front-ends that forward here.
 *
 * The client owns a [CacheStore] keyed by `(tableId, cacheKey)`. On mutation,
 * cache invalidation cascades per table.
 *
 * Query encoding note: Ktor's `URLBuilder` percent-encodes `+` in query values
 * as `%2B` (verified by `TestClientUrlEncoding`) — formulas like `LEN({f})+1`
 * survive the round-trip. (The Swift target needed a manual fix for this.)
 *
 * Lifecycle: implements [Closeable]. When no [httpClient] is injected, the
 * client constructs (and owns) a CIO-backed engine whose threads are released
 * by [close]. Injected clients are the caller's to close — [close] never
 * touches them.
 *
 * Airtable REST reference: https://airtable.com/developers/web/api/
 */
class AirtableClient(
    val baseId: String,
    val apiKey: String,
    val apiBase: String = "https://api.airtable.com/v0",
    val cache: CacheStore = CacheStore(),
    /**
     * Max retries for transient HTTP failures (429, 5xx). Total wait is
     * roughly `baseRetryDelaySeconds * 2^attempt` up to [maxRetries].
     */
    val maxRetries: Int = 3,
    val baseRetryDelaySeconds: Double = 0.5,
    /**
     * Upper bound (seconds) on any single retry wait. Applies to both the
     * computed exponential backoff and a server-provided `Retry-After`.
     */
    val maxRetryDelaySeconds: Double = 30.0,
    /**
     * Per-request timeout (seconds) installed on the default-constructed
     * engine. Ignored when an [httpClient] is injected — configure timeouts
     * on the injected client instead.
     */
    val requestTimeoutSeconds: Double = 30.0,
    httpClient: HttpClient? = null,
) : Closeable {
    init {
        if (apiKey.isBlank() || baseId.isBlank()) throw AirtableException.MissingCredentials()
    }

    /**
     * Convenience constructor wiring a cache with the given TTL (seconds).
     * Matches the other targets' `with_cache(apiKey, baseId, seconds)` shape.
     */
    constructor(
        baseId: String,
        apiKey: String,
        cacheSeconds: Double,
        maxEntries: Int? = null,
    ) : this(baseId = baseId, apiKey = apiKey, cache = CacheStore(defaultTtlSeconds = cacheSeconds, maxEntries = maxEntries))

    /** True when this instance constructed (and therefore owns) its [HttpClient]. */
    private val ownsHttp = httpClient == null

    private val http: HttpClient =
        httpClient ?: HttpClient(CIO) {
            install(HttpTimeout) {
                requestTimeoutMillis = (requestTimeoutSeconds * 1000).toLong()
            }
        }

    /**
     * Close the underlying [HttpClient] when this instance created it (no
     * [httpClient] was injected). Injected clients are the caller's to close;
     * this is a no-op for them. Safe to call more than once.
     */
    override fun close() {
        if (ownsHttp) http.close()
    }

    // region Cache controls

    /** Drop every cached payload across every table. */
    suspend fun invalidateAllCaches() = cache.invalidate(CacheStore.Scope.All)

    /** Drop cached payloads for a single table. */
    suspend fun invalidateCache(tableId: String) = cache.invalidate(CacheStore.Scope.Table(tableId))

    // endregion

    // region Endpoint builders

    /** `/<baseId>/<tableId>` for list / create. */
    internal fun tableUrl(
        tableId: String,
        params: List<Pair<String, String>> = emptyList(),
    ): Url {
        val builder = URLBuilder(apiBase)
        builder.appendPathSegments(baseId, tableId)
        for ((name, value) in params) builder.parameters.append(name, value)
        return builder.build()
    }

    /** `/<baseId>/<tableId>/<recordId>` for single record ops. */
    internal fun recordUrl(
        tableId: String,
        recordId: String,
        params: List<Pair<String, String>> = emptyList(),
    ): Url {
        val builder = URLBuilder(apiBase)
        builder.appendPathSegments(baseId, tableId, recordId)
        for ((name, value) in params) builder.parameters.append(name, value)
        return builder.build()
    }

    // endregion

    // region Request execution

    /**
     * Send a request with bearer auth and automatic retry on 429/5xx.
     *
     * Transport failures (connect/DNS/socket errors, request timeouts) are
     * wrapped as [AirtableException.Network] so `catch (e: AirtableException)`
     * covers every failure mode; coroutine cancellation is rethrown untouched.
     */
    internal suspend fun send(
        method: HttpMethod,
        url: Url,
        body: String? = null,
    ): String {
        var attempt = 0
        while (true) {
            val response =
                try {
                    http.request(url) {
                        this.method = method
                        header(HttpHeaders.Authorization, "Bearer $apiKey")
                        if (body != null) {
                            contentType(ContentType.Application.Json)
                            setBody(body)
                        }
                    }
                } catch (e: HttpRequestTimeoutException) {
                    // Ktor's request timeout must be wrapped *before* the
                    // CancellationException rethrow below: depending on Ktor
                    // version it can subclass CancellationException.
                    throw AirtableException.Network(e)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: IOException) {
                    throw AirtableException.Network(e)
                }
            val status = response.status.value
            if (status in 200..299) {
                return response.bodyAsText()
            }

            // Consume the error body exactly once, up front. Ktor 3.2 bodies
            // are lazy: an unread body can pin its pooled connection, so
            // retried and terminal responses alike must be drained here.
            val bodyText = runCatching { response.bodyAsText() }.getOrNull()

            val retryAfterSeconds = parseRetryAfter(response.headers["Retry-After"])
            val isRetryable = status == 429 || status in 500..599
            if (isRetryable && attempt < maxRetries) {
                val waitSeconds =
                    if (retryAfterSeconds != null) {
                        // Honor a server-provided Retry-After exactly (no jitter), capped.
                        min(retryAfterSeconds, maxRetryDelaySeconds)
                    } else {
                        val backoff = baseRetryDelaySeconds * 2.0.pow(attempt)
                        min(backoff * (0.5 + Random.nextDouble() * 0.5), maxRetryDelaySeconds)
                    }
                delay(waitSeconds.seconds)
                attempt += 1
                continue
            }

            if (status == 429) {
                throw AirtableException.RateLimited(retryAfterSeconds)
            }

            // Try to decode a structured error envelope.
            if (bodyText != null) {
                val envelope = runCatching { AirtableJson.instance.decodeFromString(AirtableErrorEnvelope.serializer(), bodyText) }.getOrNull()
                if (envelope != null) {
                    throw envelope.toAirtableException()
                }
            }
            throw AirtableException.Http(statusCode = status, body = bodyText)
        }
    }

    /**
     * Parse a `Retry-After` header: either delay-seconds (`"1.5"`) or an
     * RFC 9110 HTTP-date (`"Wed, 21 Oct 2026 07:28:00 GMT"`, converted to a
     * delta from now, floored at 0). Returns null when absent or unparseable.
     */
    private fun parseRetryAfter(headerValue: String?): Double? {
        if (headerValue == null) return null
        headerValue.toDoubleOrNull()?.let { return it }
        return runCatching {
            val target = ZonedDateTime.parse(headerValue, DateTimeFormatter.RFC_1123_DATE_TIME)
            max(0.0, (target.toInstant().toEpochMilli() - System.currentTimeMillis()) / 1000.0)
        }.getOrNull()
    }

    // endregion

    // region Record endpoints (raw-JSON level)
    //
    // These return raw JSON text so typed and dict table wrappers can decode
    // into their preferred shape (model vs Fields). Cache reads happen at this
    // layer (keyed on table + query/record).

    /** Compose a stable, deterministic cache key from [AirtableQuery]. */
    private fun cacheKeyForQuery(query: AirtableQuery): String {
        // Encode both halves so a formula containing `=`/`&` cannot collide
        // with a structurally different query's key (myairtable-dmiw).
        val items =
            query
                .toParameters()
                .map { "${it.first.encodeURLParameter()}=${it.second.encodeURLParameter()}" }
                .sorted()
                .joinToString("&")
        return "list?$items"
    }

    /**
     * GET list records. Returns the raw response (envelope:
     * `{records: [...], offset: "..."}`). When the cache TTL is positive,
     * cached payloads are returned before hitting the API.
     */
    suspend fun listRecords(
        tableId: String,
        query: AirtableQuery = AirtableQuery(),
    ): String {
        val key = CacheStore.Key(tableId = tableId, keyedOn = cacheKeyForQuery(query))
        cache.get(key)?.let { return it }
        val payload = send(HttpMethod.Get, tableUrl(tableId, query.toParameters()))
        // Multi-page payloads carry a server-side `offset` continuation token
        // that expires after a few minutes — caching one would serve a dead
        // token on the next hit and fail the follow-up page fetch
        // (myairtable-p7eb). Cache complete single-page payloads only.
        if (!hasContinuationOffset(payload)) {
            cache.set(key, payload)
        }
        return payload
    }

    @Serializable
    private data class OffsetProbe(
        val offset: String? = null,
    )

    private fun hasContinuationOffset(payload: String): Boolean =
        runCatching { AirtableJson.instance.decodeFromString<OffsetProbe>(payload).offset }
            .getOrNull()
            .isNullOrEmpty()
            .not()

    /**
     * GET a single record. Returns the raw response (envelope:
     * `{id, createdTime, fields}`). Always sets `returnFieldsByFieldId=true`
     * so the response keys match the generator's field-ID constants.
     */
    suspend fun getRecord(
        tableId: String,
        recordId: String,
    ): String {
        val key = CacheStore.Key(tableId = tableId, keyedOn = "rec:$recordId")
        cache.get(key)?.let { return it }
        val url = recordUrl(tableId, recordId, listOf("returnFieldsByFieldId" to "true"))
        val payload = send(HttpMethod.Get, url)
        cache.set(key, payload)
        return payload
    }

    /**
     * POST to create records. [body] is a JSON `{records: [{fields: {...}},
     * ...]}` envelope. Cache is invalidated for the table on success.
     */
    suspend fun createRecords(
        tableId: String,
        body: String,
    ): String {
        val response = send(HttpMethod.Post, tableUrl(tableId), body)
        invalidateCache(tableId)
        return response
    }

    /**
     * PATCH to update records. [body] is `{records: [{id, fields}, ...]}`.
     * Cache is invalidated for the table on success.
     */
    suspend fun updateRecords(
        tableId: String,
        body: String,
    ): String {
        val response = send(HttpMethod.Patch, tableUrl(tableId), body)
        invalidateCache(tableId)
        return response
    }

    /** DELETE a single record. Cache is invalidated for the table on success. */
    suspend fun deleteRecord(
        tableId: String,
        recordId: String,
    ): String {
        val response = send(HttpMethod.Delete, recordUrl(tableId, recordId))
        invalidateCache(tableId)
        return response
    }

    /** DELETE multiple records (via `records[]` query params). */
    suspend fun deleteRecords(
        tableId: String,
        recordIds: List<String>,
    ): String {
        val params = recordIds.map { "records[]" to it }
        val response = send(HttpMethod.Delete, tableUrl(tableId, params))
        invalidateCache(tableId)
        return response
    }

    // endregion
}
