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

    private struct CreateRequestBody: Encodable {
        struct RecordPayload: Encodable {
            let fields: [String: AirtableJSONValue]
        }
        let records: [RecordPayload]
        let typecast: Bool
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
        let typecast: Bool
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

    // MARK: - Read

    /// Fetch one record by ID.
    public func getOne(_ recordId: String) async throws -> Record {
        let data = try await client.getRecord(tableId: tableId, recordId: recordId)
        let env: RawRecordEnvelope
        do {
            env = try makeDecoder().decode(RawRecordEnvelope.self, from: data)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        return toRecord(env)
    }

    /// Fetch records matching the query. Paginates internally using Airtable's
    /// `offset` token; returns the full merged list.
    public func getMany(_ query: AirtableQuery = AirtableQuery()) async throws -> [Record] {
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

    // MARK: - Write

    /// Create a single record and return the populated envelope.
    public func createOne(_ fields: Fields, typecast: Bool = false) async throws -> Record {
        let storage = fields.encodeForWire()
        let body = CreateRequestBody(
            records: [.init(fields: storage)],
            typecast: typecast,
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
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "create returned no records")
        }
        return toRecord(first)
    }

    /// Update a single record's field values.
    public func updateOne(_ recordId: String, fields: Fields, typecast: Bool = false) async throws -> Record {
        let storage = fields.encodeForWire()
        let body = UpdateRequestBody(
            records: [.init(id: recordId, fields: storage)],
            typecast: typecast,
            returnFieldsByFieldId: true
        )
        let payload = try makeEncoder().encode(body)
        let data = try await client.updateRecords(tableId: tableId, body: payload)
        let env: RawListResponse
        do {
            env = try makeDecoder().decode(RawListResponse.self, from: data)
        } catch {
            throw AirtableError.decoding(underlying: error)
        }
        guard let first = env.records.first else {
            throw AirtableError.api(code: "UNEXPECTED_RESPONSE", message: "update returned no records")
        }
        return toRecord(first)
    }

    /// Delete one record by ID.
    public func deleteOne(_ recordId: String) async throws {
        _ = try await client.deleteRecord(tableId: tableId, recordId: recordId)
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
