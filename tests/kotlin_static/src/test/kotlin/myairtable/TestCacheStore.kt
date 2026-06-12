package myairtable

import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

/**
 * K2.7 — CacheStore TTL expiry, LRU eviction, and scope invalidation.
 * Parity: Swift TestCacheStore. Uses an injected clock for TTL determinism.
 */
class TestCacheStore {
    private fun key(
        table: String = "tbl1",
        keyedOn: String = "k",
    ) = CacheStore.Key(table, keyedOn)

    @Test
    fun zeroTtlDisablesCaching() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 0.0)
            cache.set(key(), "payload")
            assertNull(cache.get(key()))
            assertEquals(0, cache.count())
        }

    @Test
    fun hitWithinTtlReturnsPayload() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0)
            cache.set(key(), "payload")
            assertEquals("payload", cache.get(key()))
        }

    @Test
    fun expiredEntryIsEvictedOnAccess() =
        runTest {
            var now = 0L
            val cache = CacheStore(defaultTtlSeconds = 1.0, nowMillis = { now })
            cache.set(key(), "payload")
            now = 2_000L
            assertNull(cache.get(key()))
            assertEquals(0, cache.count())
        }

    @Test
    fun perCallTtlOverridesDefault() =
        runTest {
            var now = 0L
            val cache = CacheStore(defaultTtlSeconds = 1.0, nowMillis = { now })
            cache.set(key(), "payload")
            now = 5_000L
            assertNotNull(cache.get(key(), ttlSeconds = 60.0))
        }

    @Test
    fun capEvictsExactlyDownToMaxEntries() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0, maxEntries = 2)
            cache.set(key(keyedOn = "a"), "1")
            cache.set(key(keyedOn = "b"), "2")
            cache.set(key(keyedOn = "c"), "3")
            assertEquals(2, cache.count())
            assertNull(cache.get(key(keyedOn = "a")), "oldest entry evicted")
            assertNotNull(cache.get(key(keyedOn = "c")))
        }

    @Test
    fun getRefreshesRecencyEvictionIsLruNotFifo() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0, maxEntries = 2)
            cache.set(key(keyedOn = "a"), "1")
            cache.set(key(keyedOn = "b"), "2")
            cache.get(key(keyedOn = "a")) // refresh "a" — "b" is now least recent
            cache.set(key(keyedOn = "c"), "3")
            assertNotNull(cache.get(key(keyedOn = "a")))
            assertNull(cache.get(key(keyedOn = "b")))
        }

    @Test
    fun setOnAnExistingKeyRefreshesRecency() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0, maxEntries = 2)
            cache.set(key(keyedOn = "a"), "1")
            cache.set(key(keyedOn = "b"), "2")
            cache.set(key(keyedOn = "a"), "1-updated") // refresh "a"
            cache.set(key(keyedOn = "c"), "3")
            assertEquals("1-updated", cache.get(key(keyedOn = "a")))
            assertNull(cache.get(key(keyedOn = "b")))
        }

    @Test
    fun tableInvalidationOnlyDropsThatTable() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0)
            cache.set(key(table = "tbl1"), "1")
            cache.set(key(table = "tbl2"), "2")
            cache.invalidate(CacheStore.Scope.Table("tbl1"))
            assertNull(cache.get(key(table = "tbl1")))
            assertNotNull(cache.get(key(table = "tbl2")))
        }

    @Test
    fun allInvalidationDropsEverything() =
        runTest {
            val cache = CacheStore(defaultTtlSeconds = 60.0)
            cache.set(key(table = "tbl1"), "1")
            cache.set(key(table = "tbl2"), "2")
            cache.clear()
            assertEquals(0, cache.count())
        }
}
