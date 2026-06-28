import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Typed record accessor paired with `DictTable`. `Sendable` struct front-end
/// for the `AirtableClient` actor — the client owns all I/O and cache state.
///
/// API shape mirrors the TS and Python targets: single-record and list
/// variants of `get` / `create` / `update` / `delete` live under the same
/// name and are distinguished by the argument type. Batch variants chunk
/// into Airtable's 10-records-per-call limit automatically.
///
/// Cache invalidation on mutation happens inside the client (see
/// `AirtableClient.createRecords` / `updateRecords` / `deleteRecord*`).
public struct OrmTable<Model: AirtableModel>: Sendable {
    /// Airtable's hard cap for create / update / delete batches.
    public static var batchSize: Int { 10 }

    public let tableId: String
    internal let client: AirtableClient

    public init(tableId: String, client: AirtableClient) {
        self.tableId = tableId
        self.client = client
    }

    // =====================================================================
    // MARK: - get (read)
    // =====================================================================

    /// Fetch one record by ID.
    public func get(_ recordId: String) async throws -> Model {
        let data = try await client.getRecord(tableId: tableId, recordId: recordId)
        return try decodeRecord(data)
    }

    /// Fetch many records by ID. Sequential because `Model` (an `@Observable`
    /// class) isn't `Sendable` and can't cross task boundaries — unlike
    /// `DictTable.get(_:)`, whose `Sendable` records allow a bounded-parallel
    /// fan-out. Airtable has no bulk-get endpoint; preserving order is cheap
    /// in sequence.
    public func get(_ recordIds: [String]) async throws -> [Model] {
        if recordIds.isEmpty { return [] }
        var collected: [Model] = []
        collected.reserveCapacity(recordIds.count)
        for id in recordIds {
            collected.append(try await self.get(id))
        }
        return collected
    }

    /// Fetch records matching the query. Paginates internally via the
    /// `offset` continuation token; returns the merged list in page-arrival
    /// order. Pass `AirtableQuery()` (the default) for all records.
    public func get(_ query: AirtableQuery = AirtableQuery()) async throws -> [Model] {
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

    // =====================================================================
    // MARK: - create
    // =====================================================================

    /// Create one record. Pass a fresh `Model` built with its initializer
    /// (e.g. `PrimaryModel(primaryKey: "x")`); only writable fields are sent.
    public func create(_ model: Model, typecast: Bool = false) async throws -> Model {
        let results = try await createBatch([model.toRecord()], typecast: typecast)
        guard let first = results.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "create returned no records")
        }
        return first
    }

    /// Create many records. Chunks into Airtable's batch limit (10).
    public func create(_ models: [Model], typecast: Bool = false) async throws -> [Model] {
        if models.isEmpty { return [] }
        let payloads = models.map { $0.toRecord() }
        var collected: [Model] = []
        for chunk in payloads.chunked(intoBatchSize: Self.batchSize) {
            collected.append(contentsOf: try await createBatch(chunk, typecast: typecast))
        }
        return collected
    }

    private func createBatch(
        _ records: [[String: AirtableJSONValue]],
        typecast: Bool = false
    ) async throws -> [Model] {
        let body = AirtableCreateBody(
            records: records.map { AirtableCreateBody.Record(fields: $0) },
            returnFieldsByFieldId: true,
            typecast: typecast ? true : nil
        )
        let payload = try makeEncoder().encode(body)
        let response = try await client.createRecords(tableId: tableId, body: payload)
        let env: AirtableListResponse<Model> = try decodeList(response)
        return env.records
    }

    // =====================================================================
    // MARK: - update
    // =====================================================================

    /// Update a single model in place. Diffs against the model's snapshot
    /// and sends only fields that changed since the last `takeSnapshot()`.
    public func update(_ model: Model, typecast: Bool = false) async throws -> Model {
        let results = try await update([model], typecast: typecast)
        guard let first = results.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "update returned no records")
        }
        return first
    }

    /// Update many models in a single call. Chunks into Airtable's batch
    /// limit (10). Each model's dirty-field diff is used as the patch set.
    /// Models with no dirty fields already match server state, so they are
    /// never PATCHed — they come back unchanged, in their original positions.
    public func update(_ models: [Model], typecast: Bool = false) async throws -> [Model] {
        if models.isEmpty { return [] }
        var results = [Model?](repeating: nil, count: models.count)
        var dirtyIndices: [Int] = []
        var patches: [AirtableUpdateBody.Record] = []
        for (index, model) in models.enumerated() {
            guard let recordId = model.id, !recordId.isEmpty else {
                throw AirtableError.api(
                    code: "UNSAVED_MODEL",
                    message: "Cannot update a model without an id"
                )
            }
            let dirty = model.dirtyFields()
            if dirty.isEmpty {
                results[index] = model
            } else {
                dirtyIndices.append(index)
                patches.append(.init(id: recordId, fields: dirty))
            }
        }

        var updated: [Model] = []
        for chunk in patches.chunked(intoBatchSize: Self.batchSize) {
            updated.append(contentsOf: try await updateBatch(chunk, typecast: typecast))
        }
        for (slot, model) in zip(dirtyIndices, updated) {
            results[slot] = model
        }
        return try results.map { model in
            guard let model = model else {
                throw AirtableError.api(
                    code: "UNEXPECTED_RESPONSE",
                    message: "update returned fewer records than requested"
                )
            }
            return model
        }
    }

    /// Update a record with an explicit field dict (bypasses dirty tracking).
    public func updateFields(
        _ recordId: String,
        _ fields: [String: AirtableJSONValue],
        typecast: Bool = false
    ) async throws -> Model {
        let patches = [AirtableUpdateBody.Record(id: recordId, fields: fields)]
        let results = try await updateBatch(patches, typecast: typecast)
        guard let first = results.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "update returned no records")
        }
        return first
    }

    private func updateBatch(
        _ records: [AirtableUpdateBody.Record],
        typecast: Bool = false
    ) async throws -> [Model] {
        let body = AirtableUpdateBody(
            records: records,
            returnFieldsByFieldId: true,
            typecast: typecast ? true : nil
        )
        let payload = try makeEncoder().encode(body)
        let response = try await client.updateRecords(tableId: tableId, body: payload)
        let env: AirtableListResponse<Model> = try decodeList(response)
        return env.records
    }

    // =====================================================================
    // MARK: - upsert
    // =====================================================================

    /// Upsert a record, matching on the supplied field IDs. Returns the
    /// model plus `wasCreated` indicating insert vs update.
    public func upsert(
        _ model: Model,
        matchFieldsToMerge: [String],
        typecast: Bool = false
    ) async throws -> (model: Model, wasCreated: Bool) {
        let body = AirtableUpsertBody(
            records: [.init(fields: model.toRecord())],
            performUpsert: .init(fieldsToMergeOn: matchFieldsToMerge),
            returnFieldsByFieldId: true,
            typecast: typecast ? true : nil
        )
        let payload = try makeEncoder().encode(body)
        // Upsert is idempotent only when a merge key determines record identity;
        // with no merge fields it behaves like an insert and must not retry 5xx.
        let response = try await client.updateRecords(
            tableId: tableId,
            body: payload,
            idempotent: !matchFieldsToMerge.isEmpty
        )
        let env: AirtableUpsertResponse<Model>
        do {
            env = try makeDecoder().decode(AirtableUpsertResponse<Model>.self, from: response)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        for model in env.records { attach(model) }
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "upsert returned no records")
        }
        let wasCreated = (env.createdRecords ?? []).contains(first.id ?? "")
        return (first, wasCreated)
    }

    // =====================================================================
    // MARK: - delete
    // =====================================================================

    /// Delete one record by ID.
    public func delete(_ recordId: String) async throws {
        _ = try await client.deleteRecord(tableId: tableId, recordId: recordId)
    }

    /// Delete many records by ID. Chunks into Airtable's batch limit (10).
    public func delete(_ recordIds: [String]) async throws {
        if recordIds.isEmpty { return }
        for chunk in recordIds.chunked(intoBatchSize: Self.batchSize) {
            _ = try await client.deleteRecords(tableId: tableId, recordIds: chunk)
        }
    }

    /// Delete a record referenced by this model's `id`.
    public func delete(_ model: Model) async throws {
        guard let id = model.id, !id.isEmpty else {
            throw AirtableError.api(
                code: "UNSAVED_MODEL",
                message: "Cannot delete an unsaved model"
            )
        }
        try await delete(id)
    }

    /// Delete many records by passing their models. Chunks by ID.
    public func delete(_ models: [Model]) async throws {
        let ids = try models.map { model -> String in
            guard let id = model.id, !id.isEmpty else {
                throw AirtableError.api(
                    code: "UNSAVED_MODEL",
                    message: "Cannot delete an unsaved model"
                )
            }
            return id
        }
        try await delete(ids)
    }

    // =====================================================================
    // MARK: - Internal helpers
    // =====================================================================

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
            for model in env.records { attach(model) }
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
        d.dateDecodingStrategy = .airtable
        return d
    }
}

// MARK: - Array chunking

extension Array {
    /// Split into consecutive batches of at most `size` elements. Used by the
    /// batch create / update / delete paths in both `OrmTable` and `DictTable`
    /// to respect Airtable's 10-per-call limit. (Named distinctly from a
    /// potential stdlib `chunked(into:)` to avoid future-ambiguity.)
    internal func chunked(intoBatchSize size: Int) -> [[Element]] {
        precondition(size > 0, "chunk size must be positive")
        if self.isEmpty { return [] }
        var out: [[Element]] = []
        out.reserveCapacity((self.count + size - 1) / size)
        var start = 0
        while start < self.count {
            let end = Swift.min(start + size, self.count)
            out.append(Array(self[start..<end]))
            start = end
        }
        return out
    }
}
