using System.Net;
using System.Net.Http;
using System.Text;

namespace MyAirtable.Tests;

/// <summary>
/// Programmable fake <see cref="HttpMessageHandler"/> for offline client tests — the C# analog of
/// Java's <c>FakeTransport</c> / Kotlin's Ktor <c>MockEngine</c>. The responder computes a canned
/// response per call (and may throw to simulate transport loss); a thread-safe request log + call
/// counter support the bounded multi-get fan-out.
/// </summary>
internal sealed class FakeTransport : HttpMessageHandler
{
    internal sealed record Canned(
        int Status,
        string Body,
        (string Name, string Value)[]? Headers = null
    )
    {
        public static Canned Ok(string body) => new(200, body);
    }

    internal sealed record RecordedRequest(HttpMethod Method, string Url, string? Body);

    private readonly Func<HttpRequestMessage, int, Canned> _responder;
    private readonly int _entryDelayMs;
    private readonly List<RecordedRequest> _requests = new();
    private int _callCount;
    private int _inFlight;
    private int _maxConcurrent;

    /// <param name="entryDelayMs">
    /// Per-request artificial latency. Set &gt; 0 to make a bounded fan-out's overlapping requests
    /// observable via <see cref="MaxConcurrent"/>; the default 0 keeps every other test instant.
    /// </param>
    public FakeTransport(Func<HttpRequestMessage, int, Canned> responder, int entryDelayMs = 0)
    {
        _responder = responder;
        _entryDelayMs = entryDelayMs;
    }

    /// <summary>Every request seen, in arrival order.</summary>
    public IReadOnlyList<RecordedRequest> RequestHistory
    {
        get
        {
            lock (_requests)
                return _requests.ToList();
        }
    }

    public int CallCount => Volatile.Read(ref _callCount);

    /// <summary>The high-water mark of simultaneously in-flight requests seen across this handler.</summary>
    public int MaxConcurrent => Volatile.Read(ref _maxConcurrent);

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken
    )
    {
        // A realistic handler observes the token; lets tests assert pre-cancel short-circuits.
        cancellationToken.ThrowIfCancellationRequested();
        var index = Interlocked.Increment(ref _callCount) - 1;
        var inFlight = Interlocked.Increment(ref _inFlight);
        UpdateMax(inFlight);
        try
        {
            var body = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
            lock (_requests)
                _requests.Add(
                    new RecordedRequest(request.Method, request.RequestUri!.ToString(), body)
                );

            if (_entryDelayMs > 0)
                await Task.Delay(_entryDelayMs, cancellationToken).ConfigureAwait(false);

            var canned = _responder(request, index); // may throw to simulate transport loss
            var response = new HttpResponseMessage((HttpStatusCode)canned.Status)
            {
                Content = new StringContent(canned.Body, Encoding.UTF8, "application/json"),
            };
            if (canned.Headers is not null)
                foreach (var (name, value) in canned.Headers)
                    response.Headers.TryAddWithoutValidation(name, value);
            return response;
        }
        finally
        {
            Interlocked.Decrement(ref _inFlight);
        }
    }

    private void UpdateMax(int observed)
    {
        int current;
        while (observed > (current = Volatile.Read(ref _maxConcurrent)))
            Interlocked.CompareExchange(ref _maxConcurrent, observed, current);
    }
}
