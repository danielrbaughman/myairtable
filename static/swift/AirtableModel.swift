import Foundation

/// Adopted by every generated `{Table}Model` class. The generator emits
/// the concrete class as `@Observable final class {Table}Model: AirtableModel`;
/// the class supplies the field storage, manual `Codable` conformance, and
/// the snapshot/dirty-tracking implementations.
///
/// `@Observable`'s macro-generated observation tracking conflicts with
/// automatic `Codable` synthesis, so all generated models implement
/// `init(from:)` and `encode(to:)` by hand (Phase 0 gate, see
/// TestCodableObservableModel.swift). Change detection for partial
/// updates is handled with an explicit snapshot dict — **not** observation
/// tracking, which is for SwiftUI binding, not wire diffing.
public protocol AirtableModel: AnyObject, Codable {
    // Table identity for the model. Generator emits: `public static let tableId = "tbl…"`.
    static var tableId: String { get }

    /// Airtable record ID. `nil` when the model has never been saved.
    var id: RecordId? { get }

    /// Server-assigned creation timestamp. `nil` when unsaved.
    var createdTime: Date? { get }

    /// `true` when the model has no server-assigned ID yet.
    var isNew: Bool { get }

    /// Airtable client attached by the table that produced this model. Set
    /// by `OrmTable` after a successful decode so `save()` / `fetch()` /
    /// `delete()` can call back without the caller threading a table through.
    /// Mirrors Rust's `ModelMeta.client` and Python's `_at_client` field.
    var _attachedClient: AirtableClient? { get set }

    /// Capture the current field values as a snapshot. Called at the end of
    /// `init(from:)` and after a successful save so subsequent `dirtyFields()`
    /// computes the diff relative to server state.
    func takeSnapshot()

    /// Fields that changed since the last snapshot, keyed by field ID.
    /// Used by `OrmTable.update(_:)` to send only what changed.
    func dirtyFields() -> [String: AirtableJSONValue]

    /// All current field values, keyed by field ID. Used for test assertions,
    /// dict serialization, and `takeSnapshot`.
    func toRecord() -> [String: AirtableJSONValue]
}

extension AirtableModel {
    public var isNew: Bool { (id ?? "").isEmpty }

    // MARK: - Fluent model-side CRUD
    //
    // Mirrors the Rust / TS / Py pattern: once a model has been produced by
    // a table (getOne / createOne / upsertOne / getMany), it carries that
    // table's client, and `save()` / `fetch()` / `delete()` need no extra
    // arguments. A model decoded directly from JSON (no table) throws on
    // these methods with `.detachedModel`.

    /// Persist the model's dirty fields back to Airtable. Requires a saved
    /// record (`id != nil`) — construct a model with its initializer and
    /// pass it to the table's `create(_:)` to insert a brand-new row.
    public func save() async throws -> Self {
        let client = try attachedClientOrThrow()
        guard let recordId = self.id, !recordId.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot save a model without an id; use Airtable.<table>.create(...) instead"
            )
        }
        _ = recordId  // silence unused-var linter in strict builds
        let orm = OrmTable<Self>(tableId: Self.tableId, client: client)
        return try await orm.update(self)
    }

    /// Re-fetch the model from the server. Returns a fresh instance — Swift
    /// protocol extensions can't mutate generic `Self` in-place.
    public func fetch() async throws -> Self {
        let client = try attachedClientOrThrow()
        guard let id = self.id, !id.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot fetch an unsaved model"
            )
        }
        let orm = OrmTable<Self>(tableId: Self.tableId, client: client)
        return try await orm.get(id)
    }

    /// Delete the record referenced by this model's `id`.
    public func delete() async throws {
        let client = try attachedClientOrThrow()
        guard let id = self.id, !id.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot delete an unsaved model"
            )
        }
        let orm = OrmTable<Self>(tableId: Self.tableId, client: client)
        try await orm.delete(id)
    }

    private func attachedClientOrThrow() throws -> AirtableClient {
        guard let client = self._attachedClient else {
            throw AirtableError.api(
                code: "DETACHED_MODEL",
                message:
                    "Model must be obtained via a table (get / create / upsert) before calling save() / fetch() / delete()"
            )
        }
        return client
    }
}

// MARK: - Wire envelopes

/// Airtable's list/create/update response shape:
/// `{"records": [{"id":..,"createdTime":..,"fields":{...}}, ...], "offset": "..."}`.
struct AirtableListResponse<M: Decodable>: Decodable {
    let records: [M]
    let offset: String?
}

/// Body for POST /records: `{records: [{fields: {<fieldId>: <value>}}], returnFieldsByFieldId: true}`.
///
/// `typecast` is intentionally omitted — Airtable's server-side default is
/// false, which matches the Rust / Python / TypeScript targets' behavior.
/// Cross-target typecast support is tracked at beads myairtable-hbph.
struct AirtableCreateBody: Encodable {
    struct Record: Encodable {
        let fields: [String: AirtableJSONValue]
    }
    let records: [Record]
    let returnFieldsByFieldId: Bool
}

/// Body for PATCH /records: `{records: [{id, fields: <dirty>}], returnFieldsByFieldId: true}`.
struct AirtableUpdateBody: Encodable {
    struct Record: Encodable {
        let id: String
        let fields: [String: AirtableJSONValue]
    }
    let records: [Record]
    let returnFieldsByFieldId: Bool
}

/// Body for POST /records with upsert: same as create + `performUpsert: { fieldsToMergeOn: [...] }`.
struct AirtableUpsertBody: Encodable {
    struct PerformUpsert: Encodable {
        let fieldsToMergeOn: [String]
    }
    struct Record: Encodable {
        let fields: [String: AirtableJSONValue]
    }
    let records: [Record]
    let performUpsert: PerformUpsert
    let returnFieldsByFieldId: Bool
}

/// Upsert response adds `createdRecords: [recordId]` / `updatedRecords: [recordId]`
/// alongside `records: [...]`. Exposed via `OrmTable.UpsertResult`.
struct AirtableUpsertResponse<M: Decodable>: Decodable {
    let records: [M]
    let createdRecords: [String]?
    let updatedRecords: [String]?
}
