import Foundation

/// Actor-owned TTL+LRU cache shared by all `OrmTable` / `DictTable` wrappers
/// on a given `AirtableClient`. Tables remain `Sendable` structs by forwarding
/// cache interactions through this actor rather than owning their own lock.
///
/// Semantics:
/// - **TTL**: `defaultTtl` (seconds). 0 disables caching. Per-call TTL
///   overrides are supported via the `ttl:` parameter on `get(_:ttl:)`.
/// - **LRU**: optional `maxEntries` cap. When set, the oldest-inserted
///   entry is evicted once the cap is exceeded.
/// - **Scope invalidation**: cascade by table, or wipe everything.
/// - **Stale reads**: entries past their TTL are removed on access
///   (lazy expiry).
public actor CacheStore {
    /// Scope of invalidation. `.all` wipes every entry; `.table` wipes every
    /// entry for one table.
    public enum Scope: Sendable {
        case all
        case table(String)
    }

    /// A composite cache key. The client produces these from `(tableId,
    /// keyedOn)`; `keyedOn` is an opaque string — for reads of a single record
    /// it's the record ID, for listRecords it's a hash of `AirtableQuery`.
    public struct Key: Hashable, Sendable {
        public let tableId: String
        public let keyedOn: String
        public init(tableId: String, keyedOn: String) {
            self.tableId = tableId
            self.keyedOn = keyedOn
        }
    }

    /// A cached payload. `Data` because the client stores the raw decoded
    /// JSON bytes and re-decodes on hit (keeps CacheStore generics-free).
    public struct Entry: Sendable {
        public let payload: Data
        public let insertedAt: Date
    }

    /// Default TTL for new entries when caller doesn't override.
    public let defaultTtl: TimeInterval

    /// Optional cap on cached entries. `nil` disables the LRU eviction path.
    public let maxEntries: Int?

    private var storage: [Key: Entry] = [:]
    // Insertion-order tracker for LRU eviction. Hit + set both touch this.
    private var insertionOrder: [Key] = []

    public init(defaultTtl: TimeInterval = 0, maxEntries: Int? = nil) {
        self.defaultTtl = defaultTtl
        self.maxEntries = maxEntries
    }

    // MARK: - Operations

    /// Look up a payload by key. Returns nil if absent or expired (and evicts
    /// the expired entry in that case). `ttl` overrides `defaultTtl` when
    /// provided.
    public func get(_ key: Key, ttl: TimeInterval? = nil) -> Data? {
        guard let entry = storage[key] else { return nil }
        let effectiveTtl = ttl ?? defaultTtl
        if effectiveTtl > 0 {
            let age = Date().timeIntervalSince(entry.insertedAt)
            if age > effectiveTtl {
                storage.removeValue(forKey: key)
                insertionOrder.removeAll { $0 == key }
                return nil
            }
        } else if effectiveTtl == 0 {
            // TTL of 0 means caching is off — never serve cached data.
            return nil
        }
        return entry.payload
    }

    /// Store `payload` at `key`. Evicts the oldest entry if `maxEntries` is set
    /// and the cap is exceeded. A no-op when `defaultTtl` is 0 — cache is off.
    public func set(_ key: Key, payload: Data) {
        guard defaultTtl > 0 else { return }
        if storage[key] == nil {
            insertionOrder.append(key)
        }
        storage[key] = Entry(payload: payload, insertedAt: Date())
        if let cap = maxEntries, storage.count > cap {
            let oldest = insertionOrder.removeFirst()
            storage.removeValue(forKey: oldest)
        }
    }

    /// Invalidate by scope.
    public func invalidate(_ scope: Scope) {
        switch scope {
        case .all:
            storage.removeAll()
            insertionOrder.removeAll()
        case .table(let tableId):
            storage = storage.filter { $0.key.tableId != tableId }
            insertionOrder.removeAll { $0.tableId == tableId }
        }
    }

    /// Current entry count.
    public func count() -> Int { storage.count }

    /// Drop everything (alias for `invalidate(.all)`).
    public func clear() {
        invalidate(.all)
    }
}
