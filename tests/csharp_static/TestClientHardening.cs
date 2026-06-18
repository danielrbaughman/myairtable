using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS11.1 — client hardening (parity with the Java/Kotlin TestClientHardening): credential
/// validation, retry/backoff on 429 + 5xx, Retry-After honoring, and transport-error wrapping.
/// Retry delays are set to 0 in the test client so retries are instant.
///
/// <para>Deviations from the JVM twins: C# has no <c>Closeable</c> client (the shared static
/// HttpClient / injected handler ownership differs), no construction-time timeout/cache validation,
/// no Retry-After cap, and integer-only Retry-After parsing — those cases are omitted. C#
/// AirtableException subclasses use reference equality (not value equality), so the equals-semantics
/// case is omitted.</para>
/// </summary>
public class TestClientHardening
{
    private const string OkBody = "{\"records\": []}";

    private static AirtableClient Client(FakeTransport transport) =>
        new(
            "appX",
            "key",
            transport,
            cacheSeconds: 0,
            baseRetryDelaySeconds: 0,
            retryJitterCapSeconds: 0
        );

    /// <summary>Answers 429 (with optional Retry-After) <paramref name="failures"/> times, then 200.</summary>
    private static FakeTransport Flaky(int failures, string? retryAfter) =>
        new(
            (_, callIndex) =>
                callIndex < failures
                    ? new FakeTransport.Canned(
                        429,
                        "{\"error\": {\"type\": \"RATE_LIMITED\", \"message\": \"slow down\"}}",
                        retryAfter is null ? null : new[] { ("Retry-After", retryAfter) }
                    )
                    : FakeTransport.Canned.Ok(OkBody)
        );

    // ---- credential validation ----

    [Fact]
    public void BlankApiKeyThrowsMissingCredentials() =>
        Assert.Throws<AirtableException.MissingCredentialsError>(() =>
            new AirtableClient("appX", "")
        );

    [Fact]
    public void BlankBaseIdThrowsMissingCredentials() =>
        Assert.Throws<AirtableException.MissingCredentialsError>(() =>
            new AirtableClient("", "key")
        );

    // ---- retry behavior ----

    [Fact]
    public async Task RateLimitedThenSuccessRetries()
    {
        var transport = Flaky(1, null);
        var payload = await Client(transport).ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(OkBody, payload);
        Assert.Equal(2, transport.CallCount);
    }

    [Fact]
    public async Task NumericRetryAfterIsHonoredAndRetries()
    {
        var transport = Flaky(1, "0");
        var payload = await Client(transport).ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(OkBody, payload);
        Assert.Equal(2, transport.CallCount);
    }

    [Fact]
    public async Task ServerErrorThenSuccessRetries()
    {
        var transport = new FakeTransport(
            (_, callIndex) =>
                callIndex < 1
                    ? new FakeTransport.Canned(503, "{\"error\": \"SERVER\"}")
                    : FakeTransport.Canned.Ok(OkBody)
        );
        var payload = await Client(transport).ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(OkBody, payload);
        Assert.Equal(2, transport.CallCount);
    }

    [Fact]
    public async Task Terminal429ThrowsRateLimitedWithParsedRetryAfter()
    {
        // Always 429 → retries exhausted (MaxRetries=4 → 5 calls) → RateLimitedError.
        var transport = Flaky(100, "0");
        var err = await Assert.ThrowsAsync<AirtableException.RateLimitedError>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery())
        );
        Assert.Equal(0.0, err.RetryAfterSeconds);
        Assert.Equal(5, transport.CallCount);
    }

    // ---- network exception wrapping ----

    [Fact]
    public async Task TransportExceptionSurfacesAsNetwork()
    {
        var transport = new FakeTransport(
            (_, _) => throw new HttpRequestException("connection reset")
        );
        var err = await Assert.ThrowsAsync<AirtableException.NetworkError>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery())
        );
        Assert.IsType<HttpRequestException>(err.InnerException);
        Assert.Contains("connection reset", err.Message);
    }

    [Fact]
    public async Task NetworkIsCaughtByTheAirtableExceptionContract()
    {
        var transport = new FakeTransport((_, _) => throw new HttpRequestException("boom"));
        await Assert.ThrowsAnyAsync<AirtableException>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery())
        );
    }
}
