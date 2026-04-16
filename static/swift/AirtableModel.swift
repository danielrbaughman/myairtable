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
