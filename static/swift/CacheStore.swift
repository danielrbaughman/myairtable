import Foundation

/// Actor-owned TTL cache shared by all `OrmTable` / `DictTable` wrappers on a
/// given `AirtableClient`. Tables remain `Sendable` structs by forwarding all
/// cache interactions to this actor rather than owning their own `Mutex`.
///
/// F2.7 scope: skeleton only — actor type + empty storage + no-op methods.
/// Full TTL + LRU + cascade-invalidation implementation lands in F9
/// (myairtable-a9y). The actor lives here now so `AirtableClient` can
/// reference it.
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

    private var storage: [Key: Entry] = [:]

    public init(defaultTtl: TimeInterval = 0) {
        self.defaultTtl = defaultTtl
    }

    // MARK: - Operations (skeleton — F9 will add real TTL/LRU logic)

    public func get(_ key: Key, ttl: TimeInterval? = nil) -> Data? {
        guard let entry = storage[key] else { return nil }
        let ttl = ttl ?? defaultTtl
        if ttl > 0 {
            let age = Date().timeIntervalSince(entry.insertedAt)
            if age > ttl {
                storage.removeValue(forKey: key)
                return nil
            }
        }
        return entry.payload
    }

    public func set(_ key: Key, payload: Data) {
        storage[key] = Entry(payload: payload, insertedAt: Date())
    }

    public func invalidate(_ scope: Scope) {
        switch scope {
        case .all:
            storage.removeAll()
        case .table(let tableId):
            storage = storage.filter { $0.key.tableId != tableId }
        }
    }

    public func count() -> Int { storage.count }
}
