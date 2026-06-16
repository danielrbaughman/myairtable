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

    // One shared HttpClient for the process (thread-safe; avoids socket exhaustion).
    private static readonly HttpClient Http = new();

    private readonly string _baseId;
    private readonly string _apiKey;

    public AirtableClient(string baseId, string apiKey, double cacheSeconds = 0)
    {
        if (string.IsNullOrEmpty(baseId))
            throw new AirtableException.MissingCredentialsError("baseId is required");
        if (string.IsNullOrEmpty(apiKey))
            throw new AirtableException.MissingCredentialsError("apiKey is required");
        _baseId = baseId;
        _apiKey = apiKey;
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
            () => SendAsync(HttpMethod.Get, url, null, ct),
            ct
        );
    }

    /// <summary>GET a single record by id (cached).</summary>
    public Task<string> GetRecordAsync(
        string tableId,
        string recordId,
        CancellationToken ct = default
    )
    {
        var url = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}/{Esc(recordId)}";
        return Cache.GetOrAddAsync(
            tableId,
            "rec:" + recordId,
            () => SendAsync(HttpMethod.Get, url, null, ct),
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
        var result = await SendAsync(HttpMethod.Post, url, body, ct).ConfigureAwait(false);
        Cache.Invalidate(tableId);
        return result;
    }

    public async Task<string> UpdateRecordsAsync(
        string tableId,
        string body,
        CancellationToken ct = default
    )
    {
        var url = $"{ApiRoot}/{Esc(_baseId)}/{Esc(tableId)}";
        var result = await SendAsync(HttpMethod.Patch, url, body, ct).ConfigureAwait(false);
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
        var result = await SendAsync(HttpMethod.Delete, url, null, ct).ConfigureAwait(false);
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
        var result = await SendAsync(HttpMethod.Delete, url, null, ct).ConfigureAwait(false);
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
        string.Join("&", query.ToParameters().Select(p => $"{p.Key}={p.Value}"));

    // ---- transport ----------------------------------------------------------

    /// <summary>
    /// Send a request with bearer auth and retry-with-jitter on 429/5xx. Throws an
    /// <see cref="AirtableException"/> subclass on a terminal failure.
    /// </summary>
    public async Task<string> SendAsync(
        HttpMethod method,
        string url,
        string? body,
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
                response = await Http.SendAsync(request, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (HttpRequestException ex)
            {
                if (attempt < MaxRetries)
                {
                    await DelayAsync(null, attempt++, ct).ConfigureAwait(false);
                    continue;
                }
                throw new AirtableException.NetworkError(ex.Message, ex);
            }
            catch (TaskCanceledException ex) // request timeout (not caller cancellation)
            {
                if (attempt < MaxRetries)
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

                if (status >= 500 && attempt < MaxRetries)
                {
                    await DelayAsync(null, attempt++, ct).ConfigureAwait(false);
                    continue;
                }

                throw ParseApiError(content)
                    ?? (AirtableException)new AirtableException.HttpError(status, content);
            }
        }
    }

    private static async Task DelayAsync(
        double? retryAfterSeconds,
        int attempt,
        CancellationToken ct
    )
    {
        var delay = retryAfterSeconds ?? BaseRetryDelaySeconds * Math.Pow(2, attempt);
        // Decorrelation jitter (Kotlin/Java parity) so concurrent clients don't stampede.
        var jitter = Random.Shared.NextDouble() * Math.Min(delay, RetryJitterCapSeconds);
        await Task.Delay(TimeSpan.FromSeconds(delay + jitter), ct).ConfigureAwait(false);
    }

    private static double? ParseRetryAfter(HttpResponseMessage response)
    {
        var ra = response.Headers.RetryAfter;
        if (ra?.Delta is { } delta)
            return delta.TotalSeconds;
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
