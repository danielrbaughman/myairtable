import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Raw-dict record accessor for an Airtable table. `Sendable` struct front-end
/// that forwards all I/O to the `AirtableClient` actor. Values flow through
/// as `Fields` (dual ID/name-keyed `[String: AirtableJSONValue]`), bypassing
/// typed `{Table}Model` decoding.
///
/// Paired with `OrmTable<T, C>` (lands in F4) — both share the same underlying
/// client. Generated `{Table}Table.dict` exposes this accessor.
public struct DictTable: Sendable {
    public let tableId: String
    public let nameToId: [String: String]
    private let client: AirtableClient

    public init(tableId: String, nameToId: [String: String] = [:], client: AirtableClient) {
        self.tableId = tableId
        self.nameToId = nameToId
        self.client = client
    }

    // MARK: - Wire envelopes

    private struct RawRecordEnvelope: Codable {
        let id: RecordId
        let createdTime: Date?
        var fields: [String: AirtableJSONValue]
    }

    private struct RawListResponse: Codable {
        let records: [RawRecordEnvelope]
        let offset: String?
    }

    // `typecast` is intentionally omitted — matches the Rust / Py / TS
    // behavior (Airtable defaults it to false). Cross-target typecast support
    // is tracked at beads myairtable-hbph.
    private struct CreateRequestBody: Encodable {
        struct RecordPayload: Encodable {
            let fields: [String: AirtableJSONValue]
        }
        let records: [RecordPayload]
        // Airtable echoes the inserted records back in the response. Setting
        // this true means the echoed fields are keyed by field ID — matching
        // what `returnFieldsByFieldId=true` does on list/get requests.
        let returnFieldsByFieldId: Bool
    }

    private struct UpdateRequestBody: Encodable {
        struct RecordPayload: Encodable {
            let id: String
            let fields: [String: AirtableJSONValue]
        }
        let records: [RecordPayload]
        let returnFieldsByFieldId: Bool
    }

    private struct DeleteSingleResponse: Codable {
        let id: String
        let deleted: Bool
    }

    /// A fully-loaded record: id + createdTime + Fields.
    public struct Record: Sendable, Equatable {
        public let id: RecordId
        public let createdTime: Date?
        public var fields: Fields

        public init(id: RecordId, createdTime: Date?, fields: Fields) {
            self.id = id
            self.createdTime = createdTime
            self.fields = fields
        }
    }

    private func toRecord(_ raw: RawRecordEnvelope) -> Record {
        Record(
            id: raw.id,
            createdTime: raw.createdTime,
            fields: Fields(raw.fields, nameToId: nameToId)
        )
    }

    /// Airtable's hard cap for create / update / delete batches.
    public static var batchSize: Int { 10 }

    // MARK: - get (read)

    /// Fetch one record by ID.
    public func get(_ recordId: String) async throws -> Record {
        let data = try await client.getRecord(tableId: tableId, recordId: recordId)
        let env: RawRecordEnvelope
        do {
            env = try makeDecoder().decode(RawRecordEnvelope.self, from: data)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        return toRecord(env)
    }

    /// Fetch many records by ID (parallel). Preserves caller-supplied order.
    public func get(_ recordIds: [String]) async throws -> [Record] {
        if recordIds.isEmpty { return [] }
        return try await withThrowingTaskGroup(of: (Int, Record).self) { group in
            for (index, id) in recordIds.enumerated() {
                group.addTask { (index, try await self.get(id)) }
            }
            var slots: [(Int, Record)] = []
            for try await pair in group { slots.append(pair) }
            slots.sort { $0.0 < $1.0 }
            return slots.map { $0.1 }
        }
    }

    /// Fetch records matching the query. Paginates internally using Airtable's
    /// `offset` token; returns the full merged list.
    public func get(_ query: AirtableQuery = AirtableQuery()) async throws -> [Record] {
        var collected: [Record] = []
        var offset: String? = nil
        repeat {
            let data: Data
            if let offset = offset {
                data = try await fetchWithOffset(query: query, offset: offset)
            } else {
                data = try await client.listRecords(tableId: tableId, query: query)
            }
            let env: RawListResponse
            do {
                env = try makeDecoder().decode(RawListResponse.self, from: data)
            } catch {
                throw AirtableError.decoding(underlying: error)
            }
            collected.append(contentsOf: env.records.map(toRecord))
            offset = (env.offset?.isEmpty == false) ? env.offset : nil
        } while offset != nil
        return collected
    }

    /// Internal helper: refetch with an `offset` continuation token appended
    /// to the query items. `AirtableQuery` intentionally doesn't model offset
    /// (it's a server-driven continuation, not a user-facing parameter), so
    /// we splice it in at the URL layer.
    private func fetchWithOffset(query: AirtableQuery, offset: String) async throws -> Data {
        var items = query.toQueryItems()
        items.append(URLQueryItem(name: "offset", value: offset))
        let url = try await client.tableURL(tableId, query: items)
        let req = await client.authorized(url)
        return try await client.send(req)
    }

    // MARK: - create

    /// Create one record and return the populated envelope.
    public func create(_ fields: Fields) async throws -> Record {
        let records = try await createBatch([fields])
        guard let first = records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "create returned no records")
        }
        return first
    }

    /// Create many records. Chunks into Airtable's 10-per-call batch limit.
    public func create(_ fields: [Fields]) async throws -> [Record] {
        if fields.isEmpty { return [] }
        var collected: [Record] = []
        for chunk in fields.chunked(intoBatchSize: Self.batchSize) {
            collected.append(contentsOf: try await createBatch(chunk))
        }
        return collected
    }

    private func createBatch(_ fields: [Fields]) async throws -> [Record] {
        let body = CreateRequestBody(
            records: fields.map { CreateRequestBody.RecordPayload(fields: $0.encodeForWire()) },
            returnFieldsByFieldId: true
        )
        let payload = try makeEncoder().encode(body)
        let data = try await client.createRecords(tableId: tableId, body: payload)
        let env: RawListResponse
        do {
            env = try makeDecoder().decode(RawListResponse.self, from: data)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        return env.records.map(toRecord)
    }

    // MARK: - update

    /// Update a single record's field values.
    public func update(_ recordId: String, fields: Fields) async throws -> Record {
        let payloads = [UpdateRequestBody.RecordPayload(id: recordId, fields: fields.encodeForWire())]
        let records = try await updateBatch(payloads)
        guard let first = records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "update returned no records")
        }
        return first
    }

    /// Update many records. Chunks into Airtable's 10-per-call batch limit.
    public func update(_ updates: [(id: String, fields: Fields)]) async throws -> [Record] {
        if updates.isEmpty { return [] }
        let payloads = updates.map {
            UpdateRequestBody.RecordPayload(id: $0.id, fields: $0.fields.encodeForWire())
        }
        var collected: [Record] = []
        for chunk in payloads.chunked(intoBatchSize: Self.batchSize) {
            collected.append(contentsOf: try await updateBatch(chunk))
        }
        return collected
    }

    private func updateBatch(_ payloads: [UpdateRequestBody.RecordPayload]) async throws -> [Record] {
        let body = UpdateRequestBody(records: payloads, returnFieldsByFieldId: true)
        let payload = try makeEncoder().encode(body)
        let data = try await client.updateRecords(tableId: tableId, body: payload)
        let env: RawListResponse
        do {
            env = try makeDecoder().decode(RawListResponse.self, from: data)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        return env.records.map(toRecord)
    }

    // MARK: - delete

    /// Delete one record by ID.
    public func delete(_ recordId: String) async throws {
        _ = try await client.deleteRecord(tableId: tableId, recordId: recordId)
    }

    /// Delete many records. Chunks into Airtable's 10-per-call batch limit.
    public func delete(_ recordIds: [String]) async throws {
        if recordIds.isEmpty { return }
        for chunk in recordIds.chunked(intoBatchSize: Self.batchSize) {
            _ = try await client.deleteRecords(tableId: tableId, recordIds: chunk)
        }
    }

    // MARK: - Coders

    private func makeEncoder() -> JSONEncoder {
        let enc = JSONEncoder()
        enc.dateEncodingStrategy = .iso8601
        return enc
    }

    private func makeDecoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return dec
    }
}

/// Extract the raw ID-keyed storage from `Fields` for wire encoding.
/// Internal because it bypasses the dual-access abstraction.
extension Fields {
    fileprivate func encodeForWire() -> [String: AirtableJSONValue] {
        // Re-encode through the singleValueContainer roundtrip to extract the
        // underlying storage. Cheap + correct.
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self),
            let dict = try? JSONDecoder().decode([String: AirtableJSONValue].self, from: data)
        else {
            return [:]
        }
        return dict
    }
}
