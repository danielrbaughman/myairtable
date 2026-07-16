// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * HTTP client for the Airtable REST API, built on the JDK's {@link java.net.http.HttpClient}. All
 * network I/O flows through this class; {@code OrmTable} / {@link DictTable} are thin front-ends
 * that forward here. Methods BLOCK the calling thread — cheap on virtual threads (Java 21+).
 *
 * <p>The client owns a {@link CacheStore} keyed by {@code (tableId, cacheKey)}. On mutation, cache
 * invalidation cascades per table.
 *
 * <p>Query encoding note: query values are encoded with {@link URLEncoder} (form encoding), which
 * percent-encodes {@code +} as {@code %2B} — formulas like {@code LEN({f})+1} survive the
 * round-trip — and encodes space as {@code +}, which Airtable decodes back to a space. Path
 * segments use RFC-3986 encoding (space as {@code %20}) via {@link #encodePathSegment}. Verified by
 * {@code TestClientUrlEncoding}. (The Swift target needed a manual fix for the {@code +} case.)
 *
 * <p>Lifecycle: implements {@link AutoCloseable}. When no {@code httpClient} is injected, the
 * client constructs (and owns) one whose resources are released by {@link #close}. Injected clients
 * are the caller's to close — {@link #close} never touches them.
 *
 * <p>Airtable REST reference: https://airtable.com/developers/web/api/
 */
public final class AirtableClient implements AutoCloseable {

  /** Upper bound (seconds) on the decorrelation jitter added to a server Retry-After (JR-M6). */
  private static final double RETRY_AFTER_JITTER_CAP_SECONDS = 1.0;

  private final String baseId;
  private final String apiKey;
  private final String apiBase;
  private final CacheStore cache;
  private final int maxRetries;
  private final double baseRetryDelaySeconds;
  private final double maxRetryDelaySeconds;
  private final Duration requestTimeout;
  private final java.net.http.HttpClient http;
  private final boolean ownsHttp;

  /** Client with caching disabled. */
  public AirtableClient(String baseId, String apiKey) {
    this(baseId, apiKey, new CacheStore());
  }

  /**
   * Convenience constructor wiring a cache with the given TTL (seconds). Matches the other targets'
   * {@code with_cache(apiKey, baseId, seconds)} shape.
   */
  public AirtableClient(String baseId, String apiKey, double cacheSeconds) {
    this(baseId, apiKey, new CacheStore(cacheSeconds));
  }

  public AirtableClient(String baseId, String apiKey, CacheStore cache) {
    this(baseId, apiKey, "https://api.airtable.com/v0", cache, 3, 0.5, 30.0, 30.0, null);
  }

  /**
   * Full constructor.
   *
   * @param maxRetries max retries for transient HTTP failures (429, 5xx); total wait is roughly
   *     {@code baseRetryDelaySeconds * 2^attempt} per retry
   * @param maxRetryDelaySeconds upper bound (seconds) on any single retry wait — applies to both
   *     the computed exponential backoff and a server-provided {@code Retry-After}
   * @param requestTimeoutSeconds per-request timeout (seconds); also applied when a client is
   *     injected (set on each request)
   * @param httpClient optional injected client (the caller's to close); {@code null} constructs an
   *     owned one
   */
  public AirtableClient(
      String baseId,
      String apiKey,
      String apiBase,
      CacheStore cache,
      int maxRetries,
      double baseRetryDelaySeconds,
      double maxRetryDelaySeconds,
      double requestTimeoutSeconds,
      java.net.http.HttpClient httpClient) {
    if (apiKey == null || apiKey.isBlank() || baseId == null || baseId.isBlank()) {
      throw new AirtableException.MissingCredentials();
    }
    // Validate numeric config up front so a bad value fails at construction with
    // a clear message, rather than as a raw IllegalArgumentException from inside
    // send() (e.g. HttpRequest.timeout rejects a non-positive Duration) (JR-M11).
    if (cache == null) {
      throw new IllegalArgumentException(
          "cache must not be null; use new CacheStore() to disable caching");
    }
    if (requestTimeoutSeconds <= 0) {
      throw new IllegalArgumentException(
          "requestTimeoutSeconds must be positive, got " + requestTimeoutSeconds);
    }
    if (maxRetries < 0) {
      throw new IllegalArgumentException("maxRetries must be >= 0, got " + maxRetries);
    }
    if (baseRetryDelaySeconds < 0 || maxRetryDelaySeconds < 0) {
      throw new IllegalArgumentException(
          "retry delays must be >= 0, got base="
              + baseRetryDelaySeconds
              + " max="
              + maxRetryDelaySeconds);
    }
    this.baseId = baseId;
    this.apiKey = apiKey;
    this.apiBase = apiBase;
    this.cache = cache;
    this.maxRetries = maxRetries;
    this.baseRetryDelaySeconds = baseRetryDelaySeconds;
    this.maxRetryDelaySeconds = maxRetryDelaySeconds;
    this.requestTimeout = Duration.ofMillis((long) (requestTimeoutSeconds * 1000));
    this.ownsHttp = httpClient == null;
    this.http = httpClient != null ? httpClient : java.net.http.HttpClient.newHttpClient();
  }

  public String getBaseId() {
    return baseId;
  }

  public CacheStore getCache() {
    return cache;
  }

  /**
   * Close the underlying {@link java.net.http.HttpClient} when this instance created it. Injected
   * clients are the caller's to close; this is a no-op for them. Safe to call more than once.
   */
  @Override
  public void close() {
    if (ownsHttp) {
      http.close();
    }
  }

  // ---- Cache controls ----

  /** Drop every cached payload across every table. */
  public void invalidateAllCaches() {
    cache.invalidateAll();
  }

  /** Drop cached payloads for a single table. */
  public void invalidateCache(String tableId) {
    cache.invalidateTable(tableId);
  }

  // ---- Endpoint builders ----

  /**
   * RFC-3986 path-segment encoding: space is {@code %20} (never {@code +}). {@link URLEncoder} is
   * form encoding, so its {@code +}-for-space output is post-corrected.
   */
  static String encodePathSegment(String segment) {
    return URLEncoder.encode(segment, StandardCharsets.UTF_8).replace("+", "%20");
  }

  /** Form encoding for query names/values: {@code +} → {@code %2B}, space → {@code +}. */
  static String encodeQueryComponent(String component) {
    return URLEncoder.encode(component, StandardCharsets.UTF_8);
  }

  private static String queryString(List<AirtableQuery.Param> params) {
    if (params.isEmpty()) {
      return "";
    }
    StringBuilder sb = new StringBuilder("?");
    for (int i = 0; i < params.size(); i++) {
      if (i > 0) {
        sb.append('&');
      }
      sb.append(encodeQueryComponent(params.get(i).name()))
          .append('=')
          .append(encodeQueryComponent(params.get(i).value()));
    }
    return sb.toString();
  }

  /** {@code /<baseId>/<tableId>} for list / create. */
  URI tableUrl(String tableId, List<AirtableQuery.Param> params) {
    return toUri(
        apiBase
            + "/"
            + encodePathSegment(baseId)
            + "/"
            + encodePathSegment(tableId)
            + queryString(params));
  }

  /** {@code /<baseId>/<tableId>/<recordId>} for single record ops. */
  URI recordUrl(String tableId, String recordId, List<AirtableQuery.Param> params) {
    return toUri(
        apiBase
            + "/"
            + encodePathSegment(baseId)
            + "/"
            + encodePathSegment(tableId)
            + "/"
            + encodePathSegment(recordId)
            + queryString(params));
  }

  private static URI toUri(String url) {
    try {
      return URI.create(url);
    } catch (IllegalArgumentException e) {
      throw new AirtableException.InvalidUrl();
    }
  }

  // ---- Request execution ----

  /**
   * Send a request with bearer auth and automatic retry on 429/5xx. Defaults to the idempotent
   * retry policy — safe for GETs, which is what the table front-ends route through this overload.
   *
   * @see #send(String, URI, String, boolean)
   */
  String send(String method, URI url, String body) {
    return send(method, url, body, true);
  }

  /**
   * Send a request with bearer auth and automatic retry.
   *
   * <p>Retry policy (unified spec, child kx1m): a 429 is ALWAYS retried — the server rejected the
   * request, so nothing was applied. A 5xx or a transport/IO error is retried ONLY when {@code
   * idempotent} is true; for a non-idempotent request (record creation, or an upsert with no
   * merge-on fields) a retry could duplicate the write, so the error is surfaced immediately. We do
   * NOT try to distinguish connect-before-send from a read-timeout (not portably available across
   * the sibling targets); the conservative uniform rule above is correct.
   *
   * <p>Transport failures (connect/DNS/socket errors, request timeouts) are wrapped as {@link
   * AirtableException.Network} so {@code catch (AirtableException e)} covers every failure mode.
   * Thread interruption is re-asserted before wrapping.
   *
   * @param idempotent whether retrying the request is safe (GET / list / get-by-id / update-by-id /
   *     delete / upsert-with-merge-fields). {@code false} for create (POST) and merge-less upsert.
   */
  String send(String method, URI url, String body, boolean idempotent) {
    int attempt = 0;
    while (true) {
      HttpResponse<String> response;
      try {
        HttpRequest.Builder builder =
            HttpRequest.newBuilder(url)
                .timeout(requestTimeout)
                .header("Authorization", "Bearer " + apiKey);
        if (body != null) {
          builder
              .header("Content-Type", "application/json")
              .method(method, HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
        } else {
          builder.method(method, HttpRequest.BodyPublishers.noBody());
        }
        response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
      } catch (IOException e) {
        throw new AirtableException.Network(e);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new AirtableException.Network(e);
      }

      int status = response.statusCode();
      if (status >= 200 && status <= 299) {
        return response.body();
      }

      String bodyText = response.body();
      Double retryAfterSeconds =
          parseRetryAfter(response.headers().firstValue("Retry-After").orElse(null));
      // 429 is always retryable (rejected, nothing applied). A 5xx is retryable
      // only for an idempotent request — retrying a failed non-idempotent write
      // could duplicate it (unified retry spec, child kx1m).
      boolean isRetryable = status == 429 || (idempotent && status >= 500 && status <= 599);
      if (isRetryable && attempt < maxRetries) {
        double waitSeconds;
        if (retryAfterSeconds != null) {
          // Honor a server-provided Retry-After, floored at 0 (a negative/garbage
          // numeric header must never reach Thread.sleep — it would throw
          // IllegalArgumentException and escape the "catch AirtableException
          // covers every failure" contract, JR-M4), then add a small proportional
          // jitter so concurrent callers fanning out across virtual threads don't
          // all wake on the same millisecond and re-stampede the API (JR-M6). The
          // jitter is bounded by RETRY_AFTER_JITTER_CAP_SECONDS so it stays a
          // decorrelation nudge, never a material delay.
          double floored = Math.max(0.0, retryAfterSeconds);
          double jitter =
              java.util.concurrent.ThreadLocalRandom.current().nextDouble()
                  * Math.min(floored, RETRY_AFTER_JITTER_CAP_SECONDS);
          waitSeconds = Math.min(floored + jitter, maxRetryDelaySeconds);
        } else {
          double backoff = baseRetryDelaySeconds * Math.pow(2.0, attempt);
          waitSeconds =
              Math.min(
                  backoff
                      * (0.5 + java.util.concurrent.ThreadLocalRandom.current().nextDouble() * 0.5),
                  maxRetryDelaySeconds);
        }
        try {
          Thread.sleep((long) (waitSeconds * 1000));
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          throw new AirtableException.Network(e);
        }
        attempt += 1;
        continue;
      }

      if (status == 429) {
        throw new AirtableException.RateLimited(retryAfterSeconds);
      }

      // Try to decode a structured error envelope.
      if (bodyText != null && !bodyText.isEmpty()) {
        try {
          AirtableErrorEnvelope envelope =
              AirtableJson.MAPPER.readValue(bodyText, AirtableErrorEnvelope.class);
          if (envelope.error() != null) {
            throw envelope.toAirtableException();
          }
        } catch (IOException ignored) {
          // Not an envelope — fall through to the raw HTTP exception.
        }
      }
      throw new AirtableException.Http(status, bodyText);
    }
  }

  /**
   * Parse a {@code Retry-After} header: either delay-seconds ({@code "1.5"}) or an RFC 9110
   * HTTP-date (converted to a delta from now, floored at 0). Returns {@code null} when absent or
   * unparseable.
   */
  private static Double parseRetryAfter(String headerValue) {
    if (headerValue == null) {
      return null;
    }
    try {
      return Double.parseDouble(headerValue);
    } catch (NumberFormatException ignored) {
      // fall through to HTTP-date
    }
    try {
      ZonedDateTime target = ZonedDateTime.parse(headerValue, DateTimeFormatter.RFC_1123_DATE_TIME);
      return Math.max(
          0.0, (target.toInstant().toEpochMilli() - System.currentTimeMillis()) / 1000.0);
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  // ---- Record endpoints (raw-JSON level) ----
  //
  // These return raw JSON text so typed and dict table wrappers can decode into their preferred
  // shape (model vs Fields). Cache reads happen at this layer (keyed on table + query/record).

  /** Compose a stable, deterministic cache key from {@link AirtableQuery}. */
  private static String cacheKeyForQuery(AirtableQuery query) {
    // Encode both halves so a formula containing `=`/`&` cannot collide with a
    // structurally different query's key.
    return "list?"
        + query.toParameters().stream()
            .map(p -> encodeQueryComponent(p.name()) + "=" + encodeQueryComponent(p.value()))
            .sorted()
            .reduce((a, b) -> a + "&" + b)
            .orElse("");
  }

  /**
   * GET list records. Returns the raw response (envelope: {@code {records: [...], offset: "..."}}).
   * When the cache TTL is positive, cached payloads are returned before hitting the API.
   */
  public String listRecords(String tableId, AirtableQuery query) {
    CacheStore.Key key = new CacheStore.Key(tableId, cacheKeyForQuery(query));
    String cached = cache.get(key);
    if (cached != null) {
      return cached;
    }
    String payload = send("GET", tableUrl(tableId, query.toParameters()), null);
    // Multi-page payloads carry a server-side `offset` continuation token that
    // expires after a few minutes — caching one would serve a dead token on the
    // next hit and fail the follow-up page fetch. Cache complete single-page
    // payloads only.
    if (!hasContinuationOffset(payload)) {
      cache.set(key, payload);
    }
    return payload;
  }

  private static boolean hasContinuationOffset(String payload) {
    try {
      JsonNode offset = AirtableJson.MAPPER.readTree(payload).path("offset");
      return offset.isTextual() && !offset.asText().isEmpty();
    } catch (IOException e) {
      return false;
    }
  }

  /**
   * GET a single record. Returns the raw response (envelope: {@code {id, createdTime, fields}}).
   * Always sets {@code returnFieldsByFieldId=true} so the response keys match the generator's
   * field-ID constants.
   */
  public String getRecord(String tableId, String recordId) {
    CacheStore.Key key = new CacheStore.Key(tableId, "rec:" + recordId);
    String cached = cache.get(key);
    if (cached != null) {
      return cached;
    }
    URI url =
        recordUrl(
            tableId, recordId, List.of(new AirtableQuery.Param("returnFieldsByFieldId", "true")));
    String payload = send("GET", url, null);
    cache.set(key, payload);
    return payload;
  }

  /**
   * POST to create records. {@code body} is a JSON {@code {records: [{fields: {...}}, ...]}}
   * envelope. Cache is invalidated for the table on success.
   */
  public String createRecords(String tableId, String body) {
    // Create is NOT idempotent — a retried POST would duplicate the records.
    String response = send("POST", tableUrl(tableId, List.of()), body, false);
    invalidateCache(tableId);
    return response;
  }

  /**
   * PATCH to update records by id. {@code body} is {@code {records: [{id, fields}, ...]}}. Update-
   * by-id is idempotent. Cache is invalidated for the table on success.
   */
  public String updateRecords(String tableId, String body) {
    return updateRecords(tableId, body, true);
  }

  /**
   * PATCH to update/upsert records. Update-by-id is idempotent; an upsert is idempotent only when
   * it carries {@code fieldsToMergeOn} (the merge key determines identity), so callers pass {@code
   * idempotent=false} for a merge-less upsert, which inserts and must not be retried on 5xx. Cache
   * is invalidated for the table on success.
   */
  public String updateRecords(String tableId, String body, boolean idempotent) {
    String response = send("PATCH", tableUrl(tableId, List.of()), body, idempotent);
    invalidateCache(tableId);
    return response;
  }

  /** DELETE a single record. Cache is invalidated for the table on success. */
  public String deleteRecord(String tableId, String recordId) {
    String response = send("DELETE", recordUrl(tableId, recordId, List.of()), null);
    invalidateCache(tableId);
    return response;
  }

  /** DELETE multiple records (via {@code records[]} query params). */
  public String deleteRecords(String tableId, List<String> recordIds) {
    List<AirtableQuery.Param> params =
        recordIds.stream().map(id -> new AirtableQuery.Param("records[]", id)).toList();
    String response = send("DELETE", tableUrl(tableId, params), null);
    invalidateCache(tableId);
    return response;
  }
}
