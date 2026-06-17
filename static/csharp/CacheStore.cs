namespace MyAirtable;

/// <summary>
/// A TTL + LRU response cache keyed by <c>(tableId, cacheKey)</c>, guarded by an async-aware
/// <see cref="SemaphoreSlim"/> (the C# analog of Kotlin's coroutine Mutex — never a blocking
/// <c>lock</c> held across an <c>await</c>). Reads use a split-lock check-fetch-store: the cache
/// is checked under the lock, released, the HTTP fetch awaited unlocked, then the result stored
/// under the lock. Disabled (pass-through) when <see cref="TtlSeconds"/> ≤ 0.
/// </summary>
public sealed class CacheStore
{
    private readonly record struct Key(string TableId, string CacheKey);

    private sealed class Entry
    {
        public required string Value { get; set; }
        public required DateTimeOffset Expiry { get; set; }
        public long Seq { get; set; }
    }

    private readonly Dictionary<Key, Entry> _entries = new();
    private readonly SemaphoreSlim _lock = new(1, 1);
    private readonly double _ttlSeconds;
    private readonly int _maxEntries;
    private long _seq;

    public CacheStore(double ttlSeconds = 0, int maxEntries = 1000)
    {
        _ttlSeconds = ttlSeconds;
        _maxEntries = maxEntries;
    }

    public double TtlSeconds => _ttlSeconds;
    public bool Enabled => _ttlSeconds > 0;

    /// <summary>
    /// Return the cached payload for the key, or await <paramref name="factory"/> and cache it.
    /// When <paramref name="shouldCache"/> is supplied and returns <c>false</c> for the fetched
    /// payload, the result is returned but NOT stored (e.g. a list page carrying a transient
    /// <c>offset</c> continuation token must not be cached — the token expires server-side).
    /// </summary>
    public async Task<string> GetOrAddAsync(
        string tableId,
        string cacheKey,
        Func<Task<string>> factory,
        CancellationToken ct = default,
        Func<string, bool>? shouldCache = null
    )
    {
        if (!Enabled)
            return await factory().ConfigureAwait(false);

        var key = new Key(tableId, cacheKey);

        await _lock.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            if (_entries.TryGetValue(key, out var hit) && hit.Expiry > DateTimeOffset.UtcNow)
            {
                hit.Seq = ++_seq;
                return hit.Value;
            }
        }
        finally
        {
            _lock.Release();
        }

        // Fetch OUTSIDE the lock so unrelated reads aren't serialized behind this one.
        var value = await factory().ConfigureAwait(false);

        if (shouldCache is not null && !shouldCache(value))
            return value;

        await _lock.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            _entries[key] = new Entry
            {
                Value = value,
                Expiry = DateTimeOffset.UtcNow.AddSeconds(_ttlSeconds),
                Seq = ++_seq,
            };
            EvictIfNeeded();
        }
        finally
        {
            _lock.Release();
        }
        return value;
    }

    /// <summary>
    /// Peek a cached value, lazily evicting it if past its TTL — returns <c>null</c> on miss or
    /// expiry. A non-null result proves the entry was live (not served stale); test/inspection helper.
    /// </summary>
    public string? Get(string tableId, string cacheKey)
    {
        var key = new Key(tableId, cacheKey);
        _lock.Wait();
        try
        {
            if (_entries.TryGetValue(key, out var hit))
            {
                if (hit.Expiry > DateTimeOffset.UtcNow)
                    return hit.Value;
                _entries.Remove(key); // lazy eviction past TTL
            }
            return null;
        }
        finally
        {
            _lock.Release();
        }
    }

    /// <summary>Drop every cached entry for one table (call after a mutation to that table).</summary>
    public void Invalidate(string tableId)
    {
        _lock.Wait();
        try
        {
            foreach (var k in _entries.Keys.Where(k => k.TableId == tableId).ToList())
                _entries.Remove(k);
        }
        finally
        {
            _lock.Release();
        }
    }

    /// <summary>Drop the entire cache.</summary>
    public void InvalidateAll()
    {
        _lock.Wait();
        try
        {
            _entries.Clear();
        }
        finally
        {
            _lock.Release();
        }
    }

    /// <summary>Current number of cached entries (test/inspection helper).</summary>
    public int Count
    {
        get
        {
            _lock.Wait();
            try
            {
                return _entries.Count;
            }
            finally
            {
                _lock.Release();
            }
        }
    }

    // Caller holds the lock. Evict least-recently-used entries past the cap.
    private void EvictIfNeeded()
    {
        if (_entries.Count <= _maxEntries)
            return;
        var overflow = _entries.Count - _maxEntries;
        var victims = _entries
            .OrderBy(kv => kv.Value.Seq)
            .Take(overflow)
            .Select(kv => kv.Key)
            .ToList();
        foreach (var k in victims)
            _entries.Remove(k);
    }
}
