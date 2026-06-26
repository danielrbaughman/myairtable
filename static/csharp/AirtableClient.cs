using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace MyAirtable;

/// <summary>
/// Async Airtable REST client: a single shared <see cref="HttpClient"/>, bearer auth, retry with
/// jitter on 429/5xx, and a TTL cache for reads. Returns raw JSON payloads; the generated
/// <c>DictTable</c>/<c>OrmTable</c> facades decode them. All query/path values are encoded with
/// <see cref="Uri.EscapeDataString"/> (verified live: <c>+</c>→<c>%2B</c> round-trips formulas).
/// </summary>
public sealed class AirtableClient
{
    private const string ApiRoot = "https://api.airtable.com/v0";
    private const int MaxRetries = 4;
    private const double BaseRetryDelaySeconds = 0.5;
    private const double RetryJitterCapSeconds = 1.0;

    // Hard ceiling on any single backoff, applied to BOTH the computed exponential backoff and a
    // server-supplied Retry-After. A malicious/broken `Retry-After: 999999` must never hang the call.
    private const double MaxRetryDelaySeconds = 30.0;

    // One shared HttpClient for the process (thread-safe; avoids socket exhaustion).
    private static readonly HttpClient Http = new();

    private readonly string _baseId;
    private readonly string _apiKey;
    private readonly HttpClient _http;
    private readonly double _baseRetryDelay;
    private readonly double _jitterCap;

    public AirtableClient(string baseId, string apiKey, double cacheSeconds = 0)
    {
        if (string.IsNullOrEmpty(baseId))
            throw new AirtableException.MissingCredentialsError("baseId is required");
        if (string.IsNullOrEmpty(apiKey))
            throw new AirtableException.MissingCredentialsError("apiKey is required");
        _baseId = baseId;
        _apiKey = apiKey;
        _http = Http;
        _baseRetryDelay = BaseRetryDelaySeconds;
        _jitterCap = RetryJitterCapSeconds;
        Cache = new CacheStore(cacheSeconds);
    }

    /// <summary>
    /// Test-only constructor: injects an <see cref="HttpMessageHandler"/> (a fake transport) and
    /// optionally shrinks the retry backoff so offline hardening tests don't actually sleep.
    /// Production code uses the public constructors + the shared static <see cref="HttpClient"/>.
    /// </summary>
    internal AirtableClient(
        string baseId,
        string apiKey,
        HttpMessageHandler handler,
        double cacheSeconds = 0,
        double baseRetryDelaySeconds = 0,
        double retryJitterCapSeconds = 0
    )
    {
        if (string.IsNullOrEmpty(baseId))
            throw new AirtableException.MissingCredentialsError("baseId is required");
        if (string.IsNullOrEmpty(apiKey))
            throw new AirtableException.MissingCredentialsError("apiKey is required");
        _baseId = baseId;
        _apiKey = apiKey;
        _http = new HttpClient(handler);
        _baseRetryDelay = baseRetryDelaySeconds;
        _jitterCap = retryJitterCapSeconds;
        Cache = new CacheStore(cacheSeconds);
    }

    public string BaseId => _baseId;
    public CacheStore Cache { get; }

    public void InvalidateCache(string tableId) => Cache.Invalidate(tableId);

    public void InvalidateAllCaches() => Cache.InvalidateAll();

    // ---- record endpoints ---------------------------------------------------

    /// <summary>GET one page of records for <paramref name="query"/> (cached by query).</summary>
    public Task<string> ListRecordsAsync(
        string tableId,
        AirtableQuery query,
        CancellationToken ct = default
    )
    {
        var url = TableUrl(tableId, query.ToParameters());
        return Cache.GetOrAddAsync(
            tableId,
            "list:" + CacheKeyForQuery(query),
            () => SendAsync(HttpMethod.Get, url, null, idempotent: true, ct),
            ct,
            // Don't cache a multi-page payload: its server-side `offset` continuation token
            // expires after a few minutes, so a later cache hit would replay a dead token and
            // fail the follow-up page fetch. Cache complete single-page payloads only.
            shouldCache: payload => !HasContinuationOffset(payload)
        );
    }

    private static bool HasContinuationOffset(string payload)
    {
        try
        {
            using var doc = JsonDocument.Parse(payload);
            return doc.RootElement.TryGetProperty("offset", out var offset)
                && offset.ValueKind == JsonValueKind.String
                && !string.IsNullOrEmpty(offset.GetString());
        }
        catch (JsonException)
        {
            return false;
        }
    }

    /// <summary>GET a single record by id (cached).</summary>
    public Task<string> GetRecordAsync(
        string tableId,
        string recordId,
        CancellationToken ct = default
    )
    {
        // returnFieldsByFieldId so the response keys match the generated field-id constants.
        var url =
            $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}/{Esc(recordId)}?returnFieldsByFieldId=true";
        return Cache.GetOrAddAsync(
            tableId,
            "rec:" + recordId,
            () => SendAsync(HttpMethod.Get, url, null, idempotent: true, ct),
            ct
        );
    }

    public async Task<string> CreateRecordsAsync(
        string tableId,
        string body,
        CancellationToken ct = default
    )
    {
        var url = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}";
        // create is a POST: NOT idempotent — a retried 5xx/transport error could double-insert.
        var result = await SendAsync(HttpMethod.Post, url, body, idempotent: false, ct)
            .ConfigureAwait(false);
        Cache.Invalidate(tableId);
        return result;
    }

    /// <summary>
    /// PATCH the records collection. Used by both update-by-id and upsert. Update-by-id and
    /// merge-keyed upsert are idempotent; an upsert with an empty <c>fieldsToMergeOn</c> inserts and
    /// is therefore NOT idempotent — callers pass <paramref name="idempotent"/> accordingly.
    /// </summary>
    public async Task<string> UpdateRecordsAsync(
        string tableId,
        string body,
        bool idempotent = true,
        CancellationToken ct = default
    )
    {
        var url = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}";
        var result = await SendAsync(HttpMethod.Patch, url, body, idempotent, ct)
            .ConfigureAwait(false);
        Cache.Invalidate(tableId);
        return result;
    }

    public async Task<string> DeleteRecordAsync(
        string tableId,
        string recordId,
        CancellationToken ct = default
    )
    {
        var url = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}/{Esc(recordId)}";
        var result = await SendAsync(HttpMethod.Delete, url, null, idempotent: true, ct)
            .ConfigureAwait(false);
        Cache.Invalidate(tableId);
        return result;
    }

    public async Task<string> DeleteRecordsAsync(
        string tableId,
        IReadOnlyList<string> recordIds,
        CancellationToken ct = default
    )
    {
        var pairs = recordIds.Select(id => new KeyValuePair<string, string>("records[]", id));
        var url = TableUrl(tableId, pairs);
        var result = await SendAsync(HttpMethod.Delete, url, null, idempotent: true, ct)
            .ConfigureAwait(false);
        Cache.Invalidate(tableId);
        return result;
    }

    // ---- URL building -------------------------------------------------------

    /// <summary>Build the records URL for a table with an encoded query string.</summary>
    public string TableUrl(string tableId, IEnumerable<KeyValuePair<string, string>> parameters)
    {
        var baseUrl = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}";
        var query = QueryString(parameters);
        return query.Length == 0 ? baseUrl : $"{baseUrl}?{query}";
    }

    private static string QueryString(IEnumerable<KeyValuePair<string, string>> parameters)
    {
        // Param names (e.g. fields[]) keep raw brackets — Airtable accepts them; only the
        // VALUE is percent-encoded (the encoding verified live for filterByFormula '+').
        return string.Join("&", parameters.Select(p => $"{p.Key}={Esc(p.Value)}"));
    }

    private static string Esc(string s) => Uri.EscapeDataString(s);

    private static string CacheKeyForQuery(AirtableQuery query) =>
        // Encode both halves so a value containing `=`/`&` (e.g. a filterByFormula) can't collide
        // with a structurally different query, and sort so semantically identical queries share a
        // stable key regardless of parameter order. Parity with the Java/Kotlin cacheKeyForQuery.
        string.Join(
            "&",
            query
                .ToParameters()
                .Select(p => $"{Esc(p.Key)}={Esc(p.Value)}")
                .OrderBy(s => s, StringComparer.Ordinal)
        );

    // ---- transport ----------------------------------------------------------

    /// <summary>
    /// Send a request with bearer auth and retry-with-jitter on 429/5xx. Throws an
    /// <see cref="AirtableException"/> subclass on a terminal failure.
    ///
    /// <para><paramref name="idempotent"/> classifies the request at the call site: GET/list/get,
    /// update-by-id (PATCH with ids), delete, and merge-keyed upsert are idempotent; create (POST)
    /// and an empty-merge upsert (which inserts) are not. A 429 is always retried (the server
    /// rejected the request, so nothing was applied), but 5xx and transport/IO errors are retried
    /// ONLY when idempotent — a non-idempotent retry could double-apply. We do NOT distinguish a
    /// connect-before-send failure from a read-timeout (not portably available); the conservative
    /// uniform rule is correct.</para>
    /// </summary>
    public async Task<string> SendAsync(
        HttpMethod method,
        string url,
        string? body,
        bool idempotent,
        CancellationToken ct = default
    )
    {
        var attempt = 0;
        while (true)
        {
            HttpResponseMessage response;
            try
            {
                using var request = new HttpRequestMessage(method, url);
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
                if (body is not null)
                    request.Content = new StringContent(body, Encoding.UTF8, "application/json");
                response = await _http.SendAsync(request, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (HttpRequestException ex)
            {
                if (idempotent && attempt < MaxRetries)
                {
                    await DelayAsync(null, attempt++, ct).ConfigureAwait(false);
                    continue;
                }
                throw new AirtableException.NetworkError(ex.Message, ex);
            }
            catch (TaskCanceledException ex) // request timeout (not caller cancellation)
            {
                if (idempotent && attempt < MaxRetries)
                {
                    await DelayAsync(null, attempt++, ct).ConfigureAwait(false);
                    continue;
                }
                throw new AirtableException.NetworkError("request timed out", ex);
            }

            using (response)
            {
                var content = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
                var status = (int)response.StatusCode;

                if (status is >= 200 and <= 299)
                    return content;

                if (status == 429)
                {
                    var retryAfter = ParseRetryAfter(response);
                    if (attempt < MaxRetries)
                    {
                        await DelayAsync(retryAfter, attempt++, ct).ConfigureAwait(false);
                        continue;
                    }
                    throw new AirtableException.RateLimitedError(retryAfter);
                }

                if (status >= 500 && idempotent && attempt < MaxRetries)
                {
                    await DelayAsync(null, attempt++, ct).ConfigureAwait(false);
                    continue;
                }

                throw ParseApiError(content)
                    ?? (AirtableException)new AirtableException.HttpError(status, content);
            }
        }
    }

    private async Task DelayAsync(double? retryAfterSeconds, int attempt, CancellationToken ct)
    {
        var seconds = ComputeRetryDelaySeconds(
            retryAfterSeconds,
            _baseRetryDelay,
            attempt,
            _jitterCap,
            MaxRetryDelaySeconds,
            Random.Shared.NextDouble()
        );
        await Task.Delay(TimeSpan.FromSeconds(seconds), ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Total backoff in seconds. An explicit <paramref name="retryAfterSeconds"/> (from a 429
    /// Retry-After) wins; otherwise exponential <c>baseRetryDelay * 2^attempt</c>. Decorrelation
    /// jitter of <c>rand * min(delay, jitterCap)</c> (Kotlin/Java parity) is added so concurrent
    /// clients don't stampede. The final value is capped at <paramref name="maxDelay"/> — this
    /// applies to BOTH the computed backoff AND a server-supplied Retry-After, so a broken
    /// <c>Retry-After: 999999</c> can never hang the call. A negative Retry-After is floored to 0.
    /// Pure + deterministic given <paramref name="rand"/> in [0, 1).
    /// </summary>
    internal static double ComputeRetryDelaySeconds(
        double? retryAfterSeconds,
        double baseRetryDelay,
        int attempt,
        double jitterCap,
        double maxDelay,
        double rand
    )
    {
        var delay = retryAfterSeconds is { } ra
            ? Math.Max(0, ra)
            : baseRetryDelay * Math.Pow(2, attempt);
        var jitter = rand * Math.Min(delay, jitterCap);
        return Math.Min(delay + jitter, maxDelay);
    }

    /// <summary>
    /// Parse a <c>Retry-After</c> response header per RFC 9110, handling BOTH forms: delta-seconds
    /// (exposed as <see cref="RetryConditionHeaderValue.Delta"/>) and an HTTP-date (exposed as
    /// <see cref="RetryConditionHeaderValue.Date"/>, converted to <c>max(0, date - now)</c>). The
    /// final cap is applied later in <see cref="ComputeRetryDelaySeconds"/>.
    /// </summary>
    internal static double? ParseRetryAfter(HttpResponseMessage response)
    {
        var ra = response.Headers.RetryAfter;
        if (ra?.Delta is { } delta)
            return Math.Max(0, delta.TotalSeconds);
        if (ra?.Date is { } date)
            return Math.Max(0, (date - DateTimeOffset.UtcNow).TotalSeconds);
        return null;
    }

    // Parse Airtable's {"error": "TYPE"} or {"error": {"type": ..., "message": ...}} envelope.
    private static AirtableException.ApiError? ParseApiError(string content)
    {
        try
        {
            using var doc = JsonDocument.Parse(content);
            if (!doc.RootElement.TryGetProperty("error", out var err))
                return null;
            if (err.ValueKind == JsonValueKind.String)
            {
                var code = err.GetString() ?? "";
                return new AirtableException.ApiError(code, code);
            }
            if (err.ValueKind == JsonValueKind.Object)
            {
                var code = err.TryGetProperty("type", out var t) ? t.GetString() ?? "" : "";
                var message = err.TryGetProperty("message", out var m) ? m.GetString() ?? "" : "";
                return new AirtableException.ApiError(code, message);
            }
        }
        catch (JsonException)
        {
            // Not a JSON error envelope — fall back to HttpError.
        }
        return null;
    }
}
