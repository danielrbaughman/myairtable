// CacheStore TTL+LRU semantics (PR #18 review): hits and re-writes must
// refresh recency so the maxEntries cap evicts the least-recently-used
// entry, not the oldest-inserted one.

import Foundation
import Testing

@testable import MyAirtableStatic

@Suite("CacheStore LRU")
struct TestCacheStore {
    private func key(_ name: String) -> CacheStore.Key {
        CacheStore.Key(tableId: "tbl", keyedOn: name)
    }

    private let payload = Data("x".utf8)

    @Test("get() refreshes recency — eviction is LRU, not FIFO")
    func getTouchesRecency() async {
        let cache = CacheStore(defaultTtl: 60, maxEntries: 2)
        await cache.set(key("a"), payload: payload)
        await cache.set(key("b"), payload: payload)

        // Touch "a": it becomes most-recent, so "b" is now the LRU entry.
        _ = await cache.get(key("a"))

        await cache.set(key("c"), payload: payload)  // exceeds cap → evict "b"
        #expect(await cache.get(key("a")) != nil, "touched entry must survive")
        #expect(await cache.get(key("b")) == nil, "LRU entry must be evicted")
        #expect(await cache.get(key("c")) != nil)
    }

    @Test("set() on an existing key refreshes recency")
    func setTouchesExistingKey() async {
        let cache = CacheStore(defaultTtl: 60, maxEntries: 2)
        await cache.set(key("a"), payload: payload)
        await cache.set(key("b"), payload: payload)

        // Re-write "a": under FIFO it would still be evicted first.
        await cache.set(key("a"), payload: payload)

        await cache.set(key("c"), payload: payload)  // exceeds cap → evict "b"
        #expect(await cache.get(key("a")) != nil, "re-written entry must survive")
        #expect(await cache.get(key("b")) == nil, "LRU entry must be evicted")
    }

    @Test("Cap evicts exactly down to maxEntries")
    func capHolds() async {
        let cache = CacheStore(defaultTtl: 60, maxEntries: 2)
        for name in ["a", "b", "c", "d"] {
            await cache.set(key(name), payload: payload)
        }
        #expect(await cache.count() == 2)
        #expect(await cache.get(key("c")) != nil)
        #expect(await cache.get(key("d")) != nil)
    }

    @Test("Expired entries are removed from the recency order on access")
    func expiryEvictsFromOrder() async {
        let cache = CacheStore(defaultTtl: 60, maxEntries: 2)
        await cache.set(key("a"), payload: payload)
        // Per-call ttl override of a tiny negative window forces expiry.
        _ = await cache.get(key("a"), ttl: 0.000001)
        try? await Task.sleep(nanoseconds: 10_000)
        #expect(await cache.get(key("a"), ttl: 0.000001) == nil)
        #expect(await cache.count() <= 1)
    }
}
