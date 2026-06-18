using System.Net;
using System.Net.Http.Headers;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS-review follow-up — coverage for the hardening paths the original suite left untested:
/// <see cref="CancellationToken"/> propagation (pre-cancel short-circuit + cancel-mid-backoff),
/// the exponential-backoff + decorrelation-jitter math, both Retry-After header forms, and the
/// terminal 4xx <c>{"error": ...}</c> envelope decoding into <see cref="AirtableException.ApiError"/>.
///
/// <para>The backoff/Retry-After math is exercised through the pure <c>internal</c> seams
/// (<see cref="AirtableClient.ComputeRetryDelaySeconds"/> / <see cref="AirtableClient.ParseRetryAfter"/>)
/// so the assertions are exact and never sleep.</para>
/// </summary>
public class TestClientRetryAndCancellation
{
    private const string OkBody = "{\"records\": []}";

    private static AirtableClient Client(
        FakeTransport transport,
        double baseRetryDelaySeconds = 0
    ) =>
        new(
            "appX",
            "key",
            transport,
            cacheSeconds: 0,
            baseRetryDelaySeconds: baseRetryDelaySeconds,
            retryJitterCapSeconds: 0
        );

    // ---- cancellation --------------------------------------------------------

    [Fact]
    public async Task PreCancelledTokenShortCircuitsBeforeAnyTransportCall()
    {
        var transport = new FakeTransport((_, _) => FakeTransport.Canned.Ok(OkBody));
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery(), cts.Token)
        );
        Assert.Equal(0, transport.CallCount);
    }

    [Fact]
    public async Task CancellationDuringBackoffAbortsAndDoesNotExhaustRetries()
    {
        using var cts = new CancellationTokenSource();
        // First response is a retryable 503; cancelling here means the very next thing the client
        // does is await the (30s) backoff with an already-cancelled token, which must abort.
        var transport = new FakeTransport(
            (_, _) =>
            {
                cts.Cancel();
                return new FakeTransport.Canned(503, "{\"error\": \"SERVER\"}");
            }
        );

        var ex = await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            Client(transport, baseRetryDelaySeconds: 30)
                .ListRecordsAsync("tbl1", new AirtableQuery(), cts.Token)
        );
        // Surfaces as cancellation, NOT wrapped as a NetworkError, and stops after the first attempt.
        Assert.IsNotType<AirtableException.NetworkError>(ex);
        Assert.Equal(1, transport.CallCount);
    }

    // ---- backoff math (pure) -------------------------------------------------

    [Fact]
    public void ExponentialBackoffDoublesPerAttempt()
    {
        // jitterCap 0 => jitter term is 0 regardless of rand, isolating the exponential growth.
        Assert.Equal(0.5, AirtableClient.ComputeRetryDelaySeconds(null, 0.5, 0, 0, 1.0));
        Assert.Equal(1.0, AirtableClient.ComputeRetryDelaySeconds(null, 0.5, 1, 0, 1.0));
        Assert.Equal(2.0, AirtableClient.ComputeRetryDelaySeconds(null, 0.5, 2, 0, 1.0));
        Assert.Equal(4.0, AirtableClient.ComputeRetryDelaySeconds(null, 0.5, 3, 0, 1.0));
    }

    [Fact]
    public void RetryAfterOverridesExponentialBackoff()
    {
        // base/attempt are ignored when an explicit Retry-After is supplied; jitter still applies.
        Assert.Equal(30.0, AirtableClient.ComputeRetryDelaySeconds(30.0, 0.5, 3, 0, 1.0));
        // jitter = rand * min(delay, cap) = 1.0 * min(30, 1) = 1.
        Assert.Equal(31.0, AirtableClient.ComputeRetryDelaySeconds(30.0, 0.5, 3, 1.0, 1.0));
    }

    [Fact]
    public void JitterIsBoundedByTheCapNotTheFullDelay()
    {
        // delay = 1 * 2^3 = 8; jitter is capped at 2, so rand=1 adds 2 (not 8).
        Assert.Equal(8.0, AirtableClient.ComputeRetryDelaySeconds(null, 1.0, 3, 2.0, 0.0));
        Assert.Equal(9.0, AirtableClient.ComputeRetryDelaySeconds(null, 1.0, 3, 2.0, 0.5));
        Assert.Equal(10.0, AirtableClient.ComputeRetryDelaySeconds(null, 1.0, 3, 2.0, 1.0));
    }

    // ---- Retry-After parsing -------------------------------------------------

    [Fact]
    public void ParseRetryAfterReadsNumericDeltaForm()
    {
        using var resp = new HttpResponseMessage(HttpStatusCode.TooManyRequests)
        {
            Headers = { RetryAfter = new RetryConditionHeaderValue(TimeSpan.FromSeconds(30)) },
        };
        Assert.Equal(30.0, AirtableClient.ParseRetryAfter(resp));
    }

    [Fact]
    public void ParseRetryAfterReadsHttpDateFormAndClampsToNonNegative()
    {
        using var future = new HttpResponseMessage(HttpStatusCode.TooManyRequests)
        {
            Headers =
            {
                RetryAfter = new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddSeconds(120)),
            },
        };
        var seconds = AirtableClient.ParseRetryAfter(future);
        Assert.NotNull(seconds);
        Assert.InRange(seconds!.Value, 100, 121); // ~120s minus test-execution slack

        using var past = new HttpResponseMessage(HttpStatusCode.TooManyRequests)
        {
            Headers =
            {
                RetryAfter = new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddSeconds(-60)),
            },
        };
        Assert.Equal(0.0, AirtableClient.ParseRetryAfter(past)); // clamped, never negative
    }

    [Fact]
    public void ParseRetryAfterIsNullWhenHeaderAbsent()
    {
        using var resp = new HttpResponseMessage(HttpStatusCode.TooManyRequests);
        Assert.Null(AirtableClient.ParseRetryAfter(resp));
    }

    // ---- terminal API-error decoding -----------------------------------------

    [Fact]
    public async Task TerminalObjectErrorEnvelopeIsDecodedIntoApiError()
    {
        var transport = new FakeTransport(
            (_, _) =>
                new FakeTransport.Canned(
                    422,
                    "{\"error\": {\"type\": \"INVALID_REQUEST_UNKNOWN\","
                        + " \"message\": \"Field x does not exist\"}}"
                )
        );

        var err = await Assert.ThrowsAsync<AirtableException.ApiError>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery())
        );
        Assert.Equal("INVALID_REQUEST_UNKNOWN", err.Code);
        Assert.Contains("does not exist", err.ApiMessage);
        Assert.Equal(1, transport.CallCount); // a 4xx is terminal — never retried
    }

    [Fact]
    public async Task TerminalStringErrorEnvelopeIsDecodedIntoApiError()
    {
        var transport = new FakeTransport(
            (_, _) => new FakeTransport.Canned(404, "{\"error\": \"NOT_FOUND\"}")
        );

        var err = await Assert.ThrowsAsync<AirtableException.ApiError>(() =>
            Client(transport).ListRecordsAsync("tbl1", new AirtableQuery())
        );
        Assert.Equal("NOT_FOUND", err.Code);
        Assert.Equal(1, transport.CallCount);
    }
}
