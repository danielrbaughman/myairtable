// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
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
import kotlinx.coroutines.delay
import kotlinx.serialization.Serializable
import kotlin.math.pow
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
    httpClient: HttpClient? = null,
) {
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

    private val http: HttpClient = httpClient ?: HttpClient(CIO)

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

    /** Send a request with bearer auth and automatic retry on 429/5xx. */
    internal suspend fun send(
        method: HttpMethod,
        url: Url,
        body: String? = null,
    ): String {
        var attempt = 0
        while (true) {
            val response =
                http.request(url) {
                    this.method = method
                    header(HttpHeaders.Authorization, "Bearer $apiKey")
                    if (body != null) {
                        contentType(ContentType.Application.Json)
                        setBody(body)
                    }
                }
            val status = response.status.value
            if (status in 200..299) {
                return response.bodyAsText()
            }

            val isRetryable = status == 429 || status in 500..599
            val retryAfterHeader = response.headers["Retry-After"]?.toDoubleOrNull()
            if (isRetryable && attempt < maxRetries) {
                val waitSeconds = retryAfterHeader ?: (baseRetryDelaySeconds * 2.0.pow(attempt))
                delay(waitSeconds.seconds)
                attempt += 1
                continue
            }

            if (status == 429) {
                throw AirtableException.RateLimited(retryAfterHeader)
            }

            // Try to decode a structured error envelope.
            val bodyText = runCatching { response.bodyAsText() }.getOrNull()
            if (bodyText != null) {
                val envelope = runCatching { AirtableJson.instance.decodeFromString(AirtableErrorEnvelope.serializer(), bodyText) }.getOrNull()
                if (envelope != null) {
                    throw envelope.toAirtableException()
                }
            }
            throw AirtableException.Http(statusCode = status, body = bodyText)
        }
    }

    // endregion

    // region Record endpoints (raw-JSON level)
    //
    // These return raw JSON text so typed and dict table wrappers can decode
    // into their preferred shape (model vs Fields). Cache reads happen at this
    // layer (keyed on table + query/record).

    /** Compose a stable, deterministic cache key from [AirtableQuery]. */
    private fun cacheKeyForQuery(query: AirtableQuery): String {
        val items =
            query
                .toParameters()
                .map { "${it.first}=${it.second}" }
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
