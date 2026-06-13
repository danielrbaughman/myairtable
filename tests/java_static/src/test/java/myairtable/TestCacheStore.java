package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.7 — CacheStore TTL expiry, LRU eviction, and scope invalidation. Parity:
 * Kotlin/Swift TestCacheStore. Uses an injected clock ({@link AtomicLong} behind a {@code
 * LongSupplier}) for TTL determinism.
 */
class TestCacheStore {

  private static CacheStore.Key key() {
    return key("tbl1", "k");
  }

  private static CacheStore.Key keyedOn(String keyedOn) {
    return key("tbl1", keyedOn);
  }

  private static CacheStore.Key key(String table, String keyedOn) {
    return new CacheStore.Key(table, keyedOn);
  }

  @Test
  void zeroTtlDisablesCaching() {
    CacheStore cache = new CacheStore(0.0);
    cache.set(key(), "payload");
    assertNull(cache.get(key()));
    assertEquals(0, cache.count());
  }

  @Test
  void hitWithinTtlReturnsPayload() {
    CacheStore cache = new CacheStore(60.0);
    cache.set(key(), "payload");
    assertEquals("payload", cache.get(key()));
  }

  @Test
  void ttlOnlyConstructorAppliesADefaultLruCap() {
    // JR-M5: a long-lived TTL cache must be bounded — the TTL-only ctor applies
    // DEFAULT_MAX_ENTRIES rather than growing without limit (expiry is lazy).
    CacheStore cache = new CacheStore(60.0);
    assertEquals(CacheStore.DEFAULT_MAX_ENTRIES, cache.getMaxEntries());
  }

  @Test
  void expiredEntryIsEvictedOnAccess() {
    AtomicLong now = new AtomicLong(0L);
    CacheStore cache = new CacheStore(1.0, null, now::get);
    cache.set(key(), "payload");
    now.set(2_000L);
    assertNull(cache.get(key()));
    assertEquals(0, cache.count());
  }

  @Test
  void perCallTtlOverridesDefault() {
    AtomicLong now = new AtomicLong(0L);
    CacheStore cache = new CacheStore(1.0, null, now::get);
    cache.set(key(), "payload");
    now.set(5_000L);
    assertNotNull(cache.get(key(), 60.0));
  }

  @Test
  void capEvictsExactlyDownToMaxEntries() {
    CacheStore cache = new CacheStore(60.0, 2);
    cache.set(keyedOn("a"), "1");
    cache.set(keyedOn("b"), "2");
    cache.set(keyedOn("c"), "3");
    assertEquals(2, cache.count());
    assertNull(cache.get(keyedOn("a")), "oldest entry evicted");
    assertNotNull(cache.get(keyedOn("c")));
  }

  @Test
  void getRefreshesRecencyEvictionIsLruNotFifo() {
    CacheStore cache = new CacheStore(60.0, 2);
    cache.set(keyedOn("a"), "1");
    cache.set(keyedOn("b"), "2");
    cache.get(keyedOn("a")); // refresh "a" — "b" is now least recent
    cache.set(keyedOn("c"), "3");
    assertNotNull(cache.get(keyedOn("a")));
    assertNull(cache.get(keyedOn("b")));
  }

  @Test
  void setOnAnExistingKeyRefreshesRecency() {
    CacheStore cache = new CacheStore(60.0, 2);
    cache.set(keyedOn("a"), "1");
    cache.set(keyedOn("b"), "2");
    cache.set(keyedOn("a"), "1-updated"); // refresh "a"
    cache.set(keyedOn("c"), "3");
    assertEquals("1-updated", cache.get(keyedOn("a")));
    assertNull(cache.get(keyedOn("b")));
  }

  @Test
  void tableInvalidationOnlyDropsThatTable() {
    CacheStore cache = new CacheStore(60.0);
    cache.set(key("tbl1", "k"), "1");
    cache.set(key("tbl2", "k"), "2");
    cache.invalidateTable("tbl1");
    assertNull(cache.get(key("tbl1", "k")));
    assertNotNull(cache.get(key("tbl2", "k")));
  }

  @Test
  void allInvalidationDropsEverything() {
    CacheStore cache = new CacheStore(60.0);
    cache.set(key("tbl1", "k"), "1");
    cache.set(key("tbl2", "k"), "2");
    cache.clear();
    assertEquals(0, cache.count());
  }
}
