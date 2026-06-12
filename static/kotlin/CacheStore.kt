// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * TTL+LRU cache shared by all [OrmTable]/[DictTable] wrappers on a given
 * [AirtableClient]. All access is guarded by a coroutine [Mutex], so the
 * store is safe to share across coroutines (the Kotlin analog of the Swift
 * target's `CacheStore` actor).
 *
 * Semantics:
 * - **TTL**: [defaultTtlSeconds]. 0 disables caching. Per-call TTL overrides
 *   are supported via the `ttlSeconds` parameter on [get].
 * - **LRU**: optional [maxEntries] cap. When set, the least-recently-used
 *   entry is evicted once the cap is exceeded. Both hits and writes refresh
 *   an entry's recency.
 * - **Scope invalidation**: cascade by table, or wipe everything.
 * - **Stale reads**: entries past their TTL are removed on access (lazy expiry).
 */
class CacheStore(
    /** Default TTL in seconds for new entries. 0 = caching off. */
    val defaultTtlSeconds: Double = 0.0,
    /** Optional cap on cached entries. `null` disables the LRU eviction path. */
    val maxEntries: Int? = null,
    /** Clock injection point for tests. */
    private val nowMillis: () -> Long = System::currentTimeMillis,
) {
    /** Scope of invalidation: everything, or every entry for one table. */
    sealed interface Scope {
        data object All : Scope

        data class Table(
            val tableId: String,
        ) : Scope
    }

    /**
     * A composite cache key. The client produces these from `(tableId,
     * keyedOn)`; `keyedOn` is an opaque string — for reads of a single record
     * it's the record ID, for listRecords it's derived from [AirtableQuery].
     */
    data class Key(
        val tableId: String,
        val keyedOn: String,
    )

    /**
     * A cached payload. Raw JSON text — the client re-decodes on hit, which
     * keeps the store generics-free (mirrors Swift's `Data` payloads).
     */
    private data class Entry(
        val payload: String,
        val insertedAtMillis: Long,
    )

    init {
        require(maxEntries == null || maxEntries > 0) { "maxEntries must be positive (got $maxEntries); use null to disable the cap" }
    }

    private val mutex = Mutex()

    // Access-ordered LinkedHashMap gives O(1) LRU recency on both get and put
    // (the previous explicit recency deque was an O(n) scan per access).
    private val storage = LinkedHashMap<Key, Entry>(16, 0.75f, true)

    /**
     * Look up a payload by key. Returns `null` if absent or expired (and
     * evicts the expired entry in that case). `ttlSeconds` overrides
     * [defaultTtlSeconds] when provided; an effective TTL of 0 never serves
     * cached data.
     */
    suspend fun get(
        key: Key,
        ttlSeconds: Double? = null,
    ): String? =
        mutex.withLock {
            val entry = storage[key] ?: return null
            val effectiveTtl = ttlSeconds ?: defaultTtlSeconds
            if (effectiveTtl > 0) {
                val ageSeconds = (nowMillis() - entry.insertedAtMillis) / 1000.0
                if (ageSeconds > effectiveTtl) {
                    storage.remove(key)
                    return null
                }
            } else {
                // TTL of 0 means caching is off — never serve cached data.
                return null
            }
            // The access-ordered map already refreshed recency on the lookup.
            entry.payload
        }

    /**
     * Store `payload` at `key`. Evicts the least-recently-used entry if
     * [maxEntries] is set and the cap is exceeded. A no-op when
     * [defaultTtlSeconds] is 0 — cache is off.
     */
    suspend fun set(
        key: Key,
        payload: String,
    ) {
        if (defaultTtlSeconds <= 0) return
        mutex.withLock {
            storage[key] = Entry(payload, nowMillis())
            val cap = maxEntries
            if (cap != null && storage.size > cap) {
                // Eldest = least-recently-accessed (access-ordered map).
                val leastRecent = storage.keys.first()
                storage.remove(leastRecent)
            }
        }
    }

    /** Invalidate by scope. */
    suspend fun invalidate(scope: Scope) {
        mutex.withLock {
            when (scope) {
                is Scope.All -> {
                    storage.clear()
                }

                is Scope.Table -> {
                    storage.keys.removeAll { it.tableId == scope.tableId }
                }
            }
        }
    }

    /** Current entry count. */
    suspend fun count(): Int = mutex.withLock { storage.size }

    /** Drop everything (alias for `invalidate(Scope.All)`). */
    suspend fun clear() = invalidate(Scope.All)
}
