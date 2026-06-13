// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.LongSupplier;

/**
 * TTL+LRU cache shared by all {@code OrmTable}/{@link DictTable} wrappers on a given {@link
 * AirtableClient}. All access is guarded by a {@link ReentrantLock}, so the store is safe to share
 * across threads (the Java analog of the Swift target's {@code CacheStore} actor / Kotlin's
 * Mutex-guarded store).
 *
 * <p>Semantics:
 *
 * <ul>
 *   <li><b>TTL</b>: {@link #getDefaultTtlSeconds}. 0 disables caching. Per-call TTL overrides are
 *       supported via the {@code ttlSeconds} parameter on {@link #get(Key, Double)}.
 *   <li><b>LRU</b>: optional {@code maxEntries} cap. When set, the least-recently-used entry is
 *       evicted once the cap is exceeded. Both hits and writes refresh an entry's recency.
 *   <li><b>Scope invalidation</b>: cascade by table, or wipe everything.
 *   <li><b>Stale reads</b>: entries past their TTL are removed on access (lazy expiry).
 * </ul>
 */
public final class CacheStore {

  /**
   * A composite cache key. The client produces these from {@code (tableId, keyedOn)}; {@code
   * keyedOn} is an opaque string — for reads of a single record it's the record ID, for listRecords
   * it's derived from {@link AirtableQuery}.
   */
  public record Key(String tableId, String keyedOn) {}

  /**
   * A cached payload. Raw JSON text — the client re-decodes on hit, which keeps the store
   * generics-free (mirrors Swift's {@code Data} payloads).
   */
  private record Entry(String payload, long insertedAtMillis) {}

  /**
   * Default LRU cap for the TTL-only constructor. Expiry is lazy (an entry is only reclaimed on
   * access), so without a cap a long-lived client that issues many distinct queries would
   * accumulate raw JSON payloads indefinitely (JR-M5). The full constructor still accepts {@code
   * null} to opt into an unbounded cache deliberately.
   */
  public static final int DEFAULT_MAX_ENTRIES = 10_000;

  private final double defaultTtlSeconds;
  private final Integer maxEntries;
  private final LongSupplier nowMillis;
  private final ReentrantLock lock = new ReentrantLock();

  // Access-ordered LinkedHashMap gives O(1) LRU recency on both get and put.
  private final LinkedHashMap<Key, Entry> storage = new LinkedHashMap<>(16, 0.75f, true);

  /** A disabled cache (TTL 0). */
  public CacheStore() {
    this(0.0, null);
  }

  /** A TTL cache with the {@link #DEFAULT_MAX_ENTRIES} LRU cap. */
  public CacheStore(double defaultTtlSeconds) {
    this(defaultTtlSeconds, DEFAULT_MAX_ENTRIES);
  }

  public CacheStore(double defaultTtlSeconds, Integer maxEntries) {
    this(defaultTtlSeconds, maxEntries, System::currentTimeMillis);
  }

  /** Full constructor with clock injection for tests. */
  public CacheStore(double defaultTtlSeconds, Integer maxEntries, LongSupplier nowMillis) {
    if (maxEntries != null && maxEntries <= 0) {
      throw new IllegalArgumentException(
          "maxEntries must be positive (got " + maxEntries + "); use null to disable the cap");
    }
    this.defaultTtlSeconds = defaultTtlSeconds;
    this.maxEntries = maxEntries;
    this.nowMillis = nowMillis;
  }

  /** Default TTL in seconds for new entries. 0 = caching off. */
  public double getDefaultTtlSeconds() {
    return defaultTtlSeconds;
  }

  /** Optional cap on cached entries. {@code null} disables the LRU eviction path. */
  public Integer getMaxEntries() {
    return maxEntries;
  }

  /** Look up a payload by key using the default TTL. */
  public String get(Key key) {
    return get(key, null);
  }

  /**
   * Look up a payload by key. Returns {@code null} if absent or expired (and evicts the expired
   * entry in that case). {@code ttlSeconds} overrides the default when provided; an effective TTL
   * of 0 never serves cached data.
   */
  public String get(Key key, Double ttlSeconds) {
    lock.lock();
    try {
      Entry entry = storage.get(key);
      if (entry == null) {
        return null;
      }
      double effectiveTtl = ttlSeconds != null ? ttlSeconds : defaultTtlSeconds;
      if (effectiveTtl > 0) {
        double ageSeconds = (nowMillis.getAsLong() - entry.insertedAtMillis()) / 1000.0;
        if (ageSeconds > effectiveTtl) {
          storage.remove(key);
          return null;
        }
      } else {
        // TTL of 0 means caching is off — never serve cached data.
        return null;
      }
      // The access-ordered map already refreshed recency on the lookup.
      return entry.payload();
    } finally {
      lock.unlock();
    }
  }

  /**
   * Store {@code payload} at {@code key}. Evicts the least-recently-used entry if {@code
   * maxEntries} is set and the cap is exceeded. A no-op when the default TTL is 0 — cache is off.
   */
  public void set(Key key, String payload) {
    if (defaultTtlSeconds <= 0) {
      return;
    }
    lock.lock();
    try {
      storage.put(key, new Entry(payload, nowMillis.getAsLong()));
      if (maxEntries != null && storage.size() > maxEntries) {
        // Eldest = least-recently-accessed (access-ordered map).
        Iterator<Key> it = storage.keySet().iterator();
        if (it.hasNext()) {
          it.next();
          it.remove();
        }
      }
    } finally {
      lock.unlock();
    }
  }

  /** Drop every entry for one table. */
  public void invalidateTable(String tableId) {
    lock.lock();
    try {
      storage.keySet().removeIf(key -> key.tableId().equals(tableId));
    } finally {
      lock.unlock();
    }
  }

  /** Drop everything. */
  public void invalidateAll() {
    lock.lock();
    try {
      storage.clear();
    } finally {
      lock.unlock();
    }
  }

  /** Current entry count. */
  public int count() {
    lock.lock();
    try {
      return storage.size();
    } finally {
      lock.unlock();
    }
  }

  /** Drop everything (alias for {@link #invalidateAll}). */
  public void clear() {
    invalidateAll();
  }
}
