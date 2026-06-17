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
    private readonly List<RecordedRequest> _requests = new();
    private int _callCount;

    public FakeTransport(Func<HttpRequestMessage, int, Canned> responder) => _responder = responder;

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

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken
    )
    {
        var index = Interlocked.Increment(ref _callCount) - 1;
        var body = request.Content is null
            ? null
            : await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        lock (_requests)
            _requests.Add(
                new RecordedRequest(request.Method, request.RequestUri!.ToString(), body)
            );

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
}
