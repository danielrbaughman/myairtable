using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS11.1 — client read-cache policy (parity with the Java/Kotlin TestClientCachePolicy). Uses the
/// injectable <see cref="FakeTransport"/> to return canned 200s without the network. Like
/// Java/Kotlin, a list page carrying a live <c>offset</c> continuation token is NOT cached.
/// </summary>
public class TestClientCachePolicy
{
    private static AirtableClient ClientReturning(string body) =>
        new(
            "appX",
            "key",
            new FakeTransport((_, _) => FakeTransport.Canned.Ok(body)),
            cacheSeconds: 60.0
        );

    [Fact]
    public async Task SinglePagePayloadIsCached()
    {
        var client = ClientReturning("{\"records\": []}");
        await client.ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(1, client.Cache.Count);
    }

    [Fact]
    public async Task GetRecordCachingIsUnaffected()
    {
        var client = ClientReturning("{\"id\": \"recX\", \"fields\": {}}");
        await client.GetRecordAsync("tbl1", "recX");
        Assert.Equal(1, client.Cache.Count);
    }

    [Fact]
    public async Task MultiPagePayloadWithOffsetIsNotCached()
    {
        // A page carrying a live `offset` continuation token must NOT be cached — the token
        // expires server-side, so a later hit would replay a dead token. Parity with Java/Kotlin.
        var client = ClientReturning("{\"records\": [], \"offset\": \"itrABC/recXYZ\"}");
        await client.ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(0, client.Cache.Count);
    }

    [Fact]
    public async Task EmptyStringOffsetCountsAsComplete()
    {
        // An empty-string offset is not a continuation → the page is complete and cacheable.
        var client = ClientReturning("{\"records\": [], \"offset\": \"\"}");
        await client.ListRecordsAsync("tbl1", new AirtableQuery());
        Assert.Equal(1, client.Cache.Count);
    }
}
