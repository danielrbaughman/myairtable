import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Typed record accessor paired with `DictTable`. `Sendable` struct front-end
/// for the `AirtableClient` actor — the client owns all I/O and cache state.
///
/// `Model` is the generated `@Observable final class {Table}Model`. The
/// `Create` payload for `createOne` / `upsertOne` is a method-level generic
/// so the same `OrmTable<Model>` can accept whichever `Create*Model` struct
/// matches. This lets `AirtableModel` construct an `OrmTable<Self>` from a
/// model-side `save()` / `fetch()` / `delete()` call without knowing the
/// Create type up-front.
///
/// Cache invalidation on mutation happens inside the client (see
/// `AirtableClient.createRecords` / `updateRecords` / `deleteRecord*`).
public struct OrmTable<Model: AirtableModel>: Sendable {
    public let tableId: String
    internal let client: AirtableClient

    public init(tableId: String, client: AirtableClient) {
        self.tableId = tableId
        self.client = client
    }

    // MARK: - Reads

    /// Fetch one record by ID and decode into `Model`.
    public func getOne(_ recordId: String) async throws -> Model {
        let data = try await client.getRecord(tableId: tableId, recordId: recordId)
        return try decodeRecord(data)
    }

    /// Fetch records matching the query. Paginates internally via the `offset`
    /// continuation token; returns the merged list in page-arrival order.
    public func getMany(_ query: AirtableQuery = AirtableQuery()) async throws -> [Model] {
        var collected: [Model] = []
        var offset: String? = nil
        repeat {
            let data: Data
            if let offset = offset {
                data = try await fetchWithOffset(query: query, offset: offset)
            } else {
                data = try await client.listRecords(tableId: tableId, query: query)
            }
            let env: AirtableListResponse<Model> = try decodeList(data)
            collected.append(contentsOf: env.records)
            offset = (env.offset?.isEmpty == false) ? env.offset : nil
        } while offset != nil
        return collected
    }

    // MARK: - Writes

    /// Create one record. `typecast: true` lets Airtable coerce user-supplied
    /// strings into matching single-select / collaborator / attachment values.
    public func createOne<Create: Encodable & Sendable>(
        _ create: Create,
        typecast: Bool = false
    ) async throws -> Model {
        let body = AirtableCreateBody(
            records: [.init(fields: create)],
            typecast: typecast,
            returnFieldsByFieldId: true
        )
        let payload = try makeEncoder().encode(body)
        let response = try await client.createRecords(tableId: tableId, body: payload)
        let env: AirtableListResponse<Model> = try decodeList(response)
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "create returned no records")
        }
        return first
    }

    /// Update a model in place by diffing against its snapshot. Only fields
    /// that changed since the last `takeSnapshot()` are sent. Requires the
    /// model to have a non-empty `id`.
    public func updateOne(_ model: Model, typecast: Bool = false) async throws -> Model {
        guard let recordId = model.id, !recordId.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot update a model without an id"
            )
        }
        let dirty = model.dirtyFields()
        return try await applyUpdate(
            recordId: recordId,
            fields: dirty,
            typecast: typecast
        )
    }

    /// Update a record with an explicit field set (useful when the caller
    /// doesn't hold a `Model`, or wants to force-write specific fields).
    public func updateFields(
        _ recordId: String,
        _ fields: [String: AirtableJSONValue],
        typecast: Bool = false
    ) async throws -> Model {
        return try await applyUpdate(
            recordId: recordId,
            fields: fields,
            typecast: typecast
        )
    }

    private func applyUpdate(
        recordId: String,
        fields: [String: AirtableJSONValue],
        typecast: Bool
    ) async throws -> Model {
        let body = AirtableUpdateBody(
            records: [.init(id: recordId, fields: fields)],
            typecast: typecast,
            returnFieldsByFieldId: true
        )
        let payload = try makeEncoder().encode(body)
        let response = try await client.updateRecords(tableId: tableId, body: payload)
        let env: AirtableListResponse<Model> = try decodeList(response)
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "update returned no records")
        }
        return first
    }

    /// Upsert a record, matching on the supplied field IDs. Returns the model
    /// plus a flag indicating whether it was created or matched an existing row.
    public func upsertOne<Create: Encodable & Sendable>(
        _ create: Create,
        matchFieldsToMerge: [String],
        typecast: Bool = false
    ) async throws -> (model: Model, wasCreated: Bool) {
        let body = AirtableUpsertBody(
            records: [.init(fields: create)],
            performUpsert: .init(fieldsToMergeOn: matchFieldsToMerge),
            typecast: typecast,
            returnFieldsByFieldId: true
        )
        let payload = try makeEncoder().encode(body)
        let response = try await client.updateRecords(tableId: tableId, body: payload)
        let env: AirtableUpsertResponse<Model>
        do {
            env = try makeDecoder().decode(AirtableUpsertResponse<Model>.self, from: response)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        for model in env.records {
            attach(model)
        }
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "upsert returned no records")
        }
        let wasCreated = (env.createdRecords ?? []).contains(first.id ?? "")
        return (first, wasCreated)
    }

    // MARK: - Delete

    /// Delete one record by ID.
    public func deleteOne(_ recordId: String) async throws {
        _ = try await client.deleteRecord(tableId: tableId, recordId: recordId)
    }

    /// Delete many records in a single request. Airtable caps deleteMany at
    /// 10 record IDs per call — callers who need >10 should chunk themselves
    /// (F5 will add a chunking helper).
    public func deleteMany(_ recordIds: [String]) async throws {
        _ = try await client.deleteRecords(tableId: tableId, recordIds: recordIds)
    }

    // MARK: - Internal helpers

    private func fetchWithOffset(query: AirtableQuery, offset: String) async throws -> Data {
        var items = query.toQueryItems()
        items.append(URLQueryItem(name: "offset", value: offset))
        let url = try await client.tableURL(tableId, query: items)
        let req = await client.authorized(url)
        return try await client.send(req)
    }

    /// Attach this table's client to a freshly-decoded model so the model's
    /// save/fetch/delete methods can call back into the API without taking
    /// a table parameter.
    private func attach(_ model: Model) {
        model._attachedClient = client
    }

    private func decodeRecord(_ data: Data) throws -> Model {
        do {
            let model = try makeDecoder().decode(Model.self, from: data)
            attach(model)
            return model
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
    }

    private func decodeList(_ data: Data) throws -> AirtableListResponse<Model> {
        do {
            let env = try makeDecoder().decode(AirtableListResponse<Model>.self, from: data)
            for model in env.records {
                attach(model)
            }
            return env
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
    }

    private func makeEncoder() -> JSONEncoder {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }
}
