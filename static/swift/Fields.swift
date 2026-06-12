import Foundation

/// A raw Airtable `fields` container with **dual ID/name lookup**.
///
/// `Fields` wraps a `[String: AirtableJSONValue]` dictionary keyed by field ID
/// but accepts either an ID (e.g. `"fldABC123"`) or a name (e.g. `"Primary Key"`)
/// when looking up or mutating. Generated `{Table}Fields` enums expose both
/// `.primaryKeyId` and `.primaryKeyName` static constants so call sites can
/// use whichever is ergonomic — without sacrificing ID-stability across
/// field renames.
///
/// Matches the Rust target's `Fields` helper (static/rust/struct_table.rs).
///
/// Decoded form: JSON object keyed by field IDs (because
/// `AirtableQuery.returnFieldsByFieldId` defaults to `true`). Name-based
/// lookups require a name→ID map, which generated field-type enums provide
/// via a `nameById` / `idByName` helper.
public struct Fields: Codable, Sendable, Equatable {
    /// Storage is always keyed by Airtable field ID.
    private var storage: [String: AirtableJSONValue]

    /// Optional name→ID map provided by generated `{Table}Fields` types. When
    /// present, `get(_:)` and `set(_:_:)` accept either a field name or field
    /// ID: IDs are tried first, then names are translated to IDs.
    public var nameToId: [String: String]

    public init(
        _ storage: [String: AirtableJSONValue] = [:],
        nameToId: [String: String] = [:]
    ) {
        self.storage = storage
        self.nameToId = nameToId
    }

    /// Number of populated fields.
    public var count: Int { storage.count }

    /// All field IDs currently present.
    public var ids: [String] { Array(storage.keys) }

    // MARK: - Codable

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.storage = try container.decode([String: AirtableJSONValue].self)
        self.nameToId = [:]
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(storage)
    }

    // MARK: - Dual ID/name access

    /// Retrieve by field ID or field name. IDs are tried first; if that misses
    /// and a `nameToId` mapping is installed, the key is translated.
    public func get(_ key: String) -> AirtableJSONValue? {
        if let v = storage[key] {
            return v
        }
        if let id = nameToId[key], let v = storage[id] {
            return v
        }
        return nil
    }

    /// Store by field ID or field name. IDs pass through; names are translated
    /// via `nameToId` — if no translation is available, the name is stored
    /// as-is (Airtable will reject names on write when `returnFieldsByFieldId`
    /// is true, so this mirrors the Rust behavior of "store what you got").
    public mutating func set(_ key: String, _ value: AirtableJSONValue?) {
        // ID-first, mirroring get(): a key that is already a known field ID
        // (present in storage or among nameToId's values) is never treated as
        // a name, even if a pathological field name collides with it
        // (myairtable-hwqs; parity with the Kotlin fix from PR #19).
        let resolved =
            (storage[key] != nil || nameToId.values.contains(key))
            ? key
            : (nameToId[key] ?? key)
        if let value = value {
            storage[resolved] = value
        } else {
            storage.removeValue(forKey: resolved)
        }
    }

    public subscript(key: String) -> AirtableJSONValue? {
        get { get(key) }
        set { set(key, newValue) }
    }

    // MARK: - Typed convenience getters

    public func getString(_ key: String) -> String? {
        if case .string(let s) = get(key) { return s }
        return nil
    }

    public func getInt(_ key: String) -> Int? {
        switch get(key) {
        case .int(let v): return v
        case .double(let v): return Int(v)
        default: return nil
        }
    }

    public func getDouble(_ key: String) -> Double? {
        switch get(key) {
        case .double(let v): return v
        case .int(let v): return Double(v)
        default: return nil
        }
    }

    public func getBool(_ key: String) -> Bool? {
        if case .bool(let v) = get(key) { return v }
        return nil
    }

    public func getArray(_ key: String) -> [AirtableJSONValue]? {
        if case .array(let v) = get(key) { return v }
        return nil
    }

    // MARK: - Typed convenience setters

    public mutating func setString(_ key: String, _ value: String?) {
        set(key, value.map { .string($0) })
    }

    public mutating func setInt(_ key: String, _ value: Int?) {
        set(key, value.map { .int($0) })
    }

    public mutating func setDouble(_ key: String, _ value: Double?) {
        set(key, value.map { .double($0) })
    }

    public mutating func setBool(_ key: String, _ value: Bool?) {
        set(key, value.map { .bool($0) })
    }

    public mutating func setStrings(_ key: String, _ value: [String]?) {
        set(key, value.map { .array($0.map(AirtableJSONValue.string)) })
    }
}
