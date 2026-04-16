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

    /// Capture the current field values as a snapshot. Called at the end of
    /// `init(from:)` and after a successful save so subsequent `dirtyFields()`
    /// computes the diff relative to server state.
    func takeSnapshot()

    /// Fields that changed since the last snapshot, keyed by field ID.
    /// Used by `OrmTable.updateOne` to send only what changed.
    func dirtyFields() -> [String: AirtableJSONValue]

    /// All current field values, keyed by field ID. Used for test assertions,
    /// dict serialization, and `takeSnapshot`.
    func toRecord() -> [String: AirtableJSONValue]
}

extension AirtableModel {
    public var isNew: Bool { (id ?? "").isEmpty }

    // MARK: - Fluent operations via a table
    //
    // These extensions give a "model-side" API on top of the stateless
    // `OrmTable` struct — users write `model.save(via: airtable.primary.orm)`
    // instead of `airtable.primary.orm.updateOne(model)`. Mirrors the Rust
    // target's `model.save()` / `.fetch()` / `.delete()` fluent pattern.
    //
    // Unlike Rust, we don't cache the client on the model — the caller
    // threads the table through each call. That keeps models stateless and
    // SwiftUI-binding-friendly (no hidden references, no Sendable gotchas).

    /// Persist the model. Requires an existing `id` — a brand-new model must
    /// be created via `OrmTable.createOne(_:)` with a `Create*Model` payload
    /// (we can't synthesize one from the class at runtime without reflection).
    public func save<C: Encodable & Sendable>(
        via table: OrmTable<Self, C>,
        typecast: Bool = false
    ) async throws -> Self {
        try await table.updateOne(self, typecast: typecast)
    }

    /// Re-fetch the model from the server. Returns a fresh instance — Swift
    /// protocol extensions can't mutate generic `Self` in-place.
    public func refresh<C: Encodable & Sendable>(
        via table: OrmTable<Self, C>
    ) async throws -> Self {
        guard let id = self.id, !id.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot refresh an unsaved model"
            )
        }
        return try await table.getOne(id)
    }

    /// Delete the record referenced by this model's `id`.
    public func delete<C: Encodable & Sendable>(
        via table: OrmTable<Self, C>
    ) async throws {
        guard let id = self.id, !id.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot delete an unsaved model"
            )
        }
        try await table.deleteOne(id)
    }
}

// MARK: - Wire envelopes

/// Airtable's list/create/update response shape:
/// `{"records": [{"id":..,"createdTime":..,"fields":{...}}, ...], "offset": "..."}`.
struct AirtableListResponse<M: Decodable>: Decodable {
    let records: [M]
    let offset: String?
}

/// Body for POST /records: `{records: [{fields: <Create>}], typecast: Bool, returnFieldsByFieldId: true}`.
struct AirtableCreateBody<C: Encodable>: Encodable {
    struct Record: Encodable {
        let fields: C
    }
    let records: [Record]
    let typecast: Bool
    let returnFieldsByFieldId: Bool
}

/// Body for PATCH /records: `{records: [{id, fields: <dirty>}], typecast: Bool, returnFieldsByFieldId: true}`.
struct AirtableUpdateBody: Encodable {
    struct Record: Encodable {
        let id: String
        let fields: [String: AirtableJSONValue]
    }
    let records: [Record]
    let typecast: Bool
    let returnFieldsByFieldId: Bool
}

/// Body for POST /records with upsert: same as create + `performUpsert: { fieldsToMergeOn: [...] }`.
struct AirtableUpsertBody<C: Encodable>: Encodable {
    struct PerformUpsert: Encodable {
        let fieldsToMergeOn: [String]
    }
    struct Record: Encodable {
        let fields: C
    }
    let records: [Record]
    let performUpsert: PerformUpsert
    let typecast: Bool
    let returnFieldsByFieldId: Bool
}

/// Upsert response adds `createdRecords: [recordId]` / `updatedRecords: [recordId]`
/// alongside `records: [...]`. Exposed via `OrmTable.UpsertResult`.
struct AirtableUpsertResponse<M: Decodable>: Decodable {
    let records: [M]
    let createdRecords: [String]?
    let updatedRecords: [String]?
}
