using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS11.1 — CacheStore TTL expiry, LRU eviction, and scope invalidation (parity with the
/// Java/Kotlin/Swift TestCacheStore). The C# CacheStore exposes a narrower surface than the JVM
/// twins (no public Set / injected clock / per-call-TTL / max-entries getter), so entries are
/// populated through <see cref="CacheStore.GetOrAddAsync"/> and TTL expiry uses a short real delay.
/// </summary>
public class TestCacheStore
{
    private static Task<string> SetAsync(
        CacheStore cache,
        string table,
        string key,
        string value
    ) => cache.GetOrAddAsync(table, key, () => Task.FromResult(value));

    [Fact]
    public async Task ZeroTtlDisablesCaching()
    {
        var cache = new CacheStore(0.0);
        var value = await SetAsync(cache, "tbl1", "k", "payload");
        Assert.Equal("payload", value); // factory still runs (pass-through)
        Assert.Null(cache.Get("tbl1", "k"));
        Assert.Equal(0, cache.Count);
        Assert.False(cache.Enabled);
    }

    [Fact]
    public async Task HitWithinTtlReturnsPayload()
    {
        var cache = new CacheStore(60.0);
        await SetAsync(cache, "tbl1", "k", "payload");
        Assert.Equal("payload", cache.Get("tbl1", "k"));
    }

    [Fact]
    public async Task ExpiredEntryIsEvictedOnAccess()
    {
        var cache = new CacheStore(0.1);
        await SetAsync(cache, "tbl1", "k", "payload");
        await Task.Delay(200);
        Assert.Null(cache.Get("tbl1", "k")); // lazy eviction past TTL
        Assert.Equal(0, cache.Count);
    }

    [Fact]
    public async Task CapEvictsExactlyDownToMaxEntries()
    {
        var cache = new CacheStore(60.0, 2);
        await SetAsync(cache, "tbl1", "a", "1");
        await SetAsync(cache, "tbl1", "b", "2");
        await SetAsync(cache, "tbl1", "c", "3");
        Assert.Equal(2, cache.Count);
        Assert.Null(cache.Get("tbl1", "a")); // oldest evicted
        Assert.NotNull(cache.Get("tbl1", "c"));
    }

    [Fact]
    public async Task HitRefreshesRecencyEvictionIsLruNotFifo()
    {
        var cache = new CacheStore(60.0, 2);
        await SetAsync(cache, "tbl1", "a", "1");
        await SetAsync(cache, "tbl1", "b", "2");
        await SetAsync(cache, "tbl1", "a", "1"); // GetOrAddAsync hit on "a" refreshes recency
        await SetAsync(cache, "tbl1", "c", "3"); // "b" is now least recent → evicted
        Assert.NotNull(cache.Get("tbl1", "a"));
        Assert.Null(cache.Get("tbl1", "b"));
    }

    [Fact]
    public async Task TableInvalidationOnlyDropsThatTable()
    {
        var cache = new CacheStore(60.0);
        await SetAsync(cache, "tbl1", "k", "1");
        await SetAsync(cache, "tbl2", "k", "2");
        cache.Invalidate("tbl1");
        Assert.Null(cache.Get("tbl1", "k"));
        Assert.NotNull(cache.Get("tbl2", "k"));
    }

    [Fact]
    public async Task AllInvalidationDropsEverything()
    {
        var cache = new CacheStore(60.0);
        await SetAsync(cache, "tbl1", "k", "1");
        await SetAsync(cache, "tbl2", "k", "2");
        cache.InvalidateAll();
        Assert.Equal(0, cache.Count);
    }
}
