// myairtable-hbph — `typecast` option on the public create / update / upsert
// methods (Swift target).
//
// Airtable's write API accepts a per-request `typecast` boolean. When true,
// string inputs are coerced to the cell's type (missing select options are
// created, dates/numbers parsed, etc.). The default MUST remain false so
// existing behavior is unchanged, and the key MUST be ABSENT from the wire
// body unless the caller opts in (matches Go's `if typecast { ... }`).
//
// This pins the contract by capturing the outgoing request body with a
// URLProtocol stub (same pattern as TestDictTableMultiGet's EchoRecordURLProtocol)
// and asserting `"typecast": true` is present when set and absent by default.

import Foundation
import Observation
import Testing

@testable import MyAirtableStatic

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Captures the most recent request body seen by the stubbed transport, then
/// returns a canned success envelope so the create/update/upsert calls decode.
///
/// Body capture is non-trivial under URLSession: the session usually moves
/// `httpBody` into `httpBodyStream` before the URLProtocol sees the request, so
/// we drain the stream when the direct body is nil.
private final class CaptureBodyURLProtocol: URLProtocol, @unchecked Sendable {
    /// Last captured request body, JSON-decoded into a dictionary. Guarded by
    /// `lock` because URLProtocol instances run off the test's thread.
    nonisolated(unsafe) static var lastBody: [String: Any]?
    private static let lock = NSLock()

    static func reset() {
        lock.lock()
        lastBody = nil
        lock.unlock()
    }

    static func capturedBody() -> [String: Any]? {
        lock.lock()
        defer { lock.unlock() }
        return lastBody
    }

    private static func record(_ data: Data?) {
        guard let data = data,
            let obj = try? JSONSerialization.jsonObject(with: data),
            let dict = obj as? [String: Any]
        else { return }
        lock.lock()
        lastBody = dict
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        // Prefer the direct body; fall back to draining the body stream.
        if let body = request.httpBody {
            Self.record(body)
        } else if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var collected = Data()
            let bufSize = 4096
            let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufSize)
            defer { buffer.deallocate() }
            while stream.hasBytesAvailable {
                let read = stream.read(buffer, maxLength: bufSize)
                if read <= 0 { break }
                collected.append(buffer, count: read)
            }
            Self.record(collected)
        }

        let url = request.url!
        // A records-array envelope satisfies both the list-shaped (create/update)
        // and the upsert response decoders used by OrmTable / DictTable.
        let body = Data(
            #"{"records": [{"id": "rec1", "createdTime": "2024-01-01T00:00:00Z", "fields": {"fldName001": "x"}}], "createdRecords": [], "updatedRecords": ["rec1"]}"#
                .utf8
        )
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

// Minimal `AirtableModel` mirroring the generator's emitted shape, used to drive
// OrmTable create/update/upsert through the body-building path.
@Observable
private final class TypecastModel: AirtableModel {
    static let tableId = "tblStub"

    let id: RecordId?
    let createdTime: Date?
    var name: String?

    var _attachedClient: AirtableClient?
    private var snapshot: [String: AirtableJSONValue] = [:]

    private enum CodingKeys: String, CodingKey { case id, createdTime, fields }
    private enum FieldsCodingKeys: String, CodingKey { case name = "fldName001" }

    init(id: RecordId? = nil, name: String? = nil) {
        self.id = id
        self.createdTime = nil
        self.name = name
        takeSnapshot()
    }

    required init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decodeIfPresent(String.self, forKey: .id)
        self.createdTime = try c.decodeIfPresent(Date.self, forKey: .createdTime)
        if let fields = try? c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields) {
            self.name = try fields.decodeIfPresent(String.self, forKey: .name)
        } else {
            self.name = nil
        }
        takeSnapshot()
    }

    func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(id, forKey: .id)
        var fields = c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields)
        try fields.encodeIfPresent(name, forKey: .name)
    }

    func takeSnapshot() { snapshot = toRecord() }

    func dirtyFields() -> [String: AirtableJSONValue] {
        let current = toRecord()
        var dirty: [String: AirtableJSONValue] = [:]
        for (k, v) in current where snapshot[k] != v { dirty[k] = v }
        return dirty
    }

    func toRecord() -> [String: AirtableJSONValue] {
        var out: [String: AirtableJSONValue] = [:]
        if let name = name { out["fldName001"] = .string(name) }
        return out
    }
}

// Serialized: the URLProtocol stub captures the request body into shared static
// state, so concurrent tests would race on it.
@Suite("typecast threads into the request body", .serialized)
struct TestTypecast {
    private func makeClient() -> AirtableClient {
        CaptureBodyURLProtocol.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CaptureBodyURLProtocol.self]
        return AirtableClient(
            baseId: "appX",
            apiKey: "key",
            session: URLSession(configuration: config)
        )
    }

    private func ormTable() -> OrmTable<TypecastModel> {
        OrmTable<TypecastModel>(tableId: "tblStub", client: makeClient())
    }

    private func dictTable() -> DictTable {
        DictTable(tableId: "tblStub", client: makeClient())
    }

    // MARK: - DictTable

    @Test func dictCreateDefaultOmitsTypecast() async throws {
        _ = try await dictTable().create(Fields(["fldName001": .string("a")]))
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect(body?["typecast"] == nil)
    }

    @Test func dictCreateSetIncludesTypecast() async throws {
        _ = try await dictTable().create(Fields(["fldName001": .string("a")]), typecast: true)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect((body?["typecast"] as? Bool) == true)
    }

    @Test func dictUpdateDefaultOmitsTypecast() async throws {
        _ = try await dictTable().update("rec1", fields: Fields(["fldName001": .string("a")]))
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect(body?["typecast"] == nil)
    }

    @Test func dictUpdateSetIncludesTypecast() async throws {
        _ = try await dictTable().update(
            "rec1", fields: Fields(["fldName001": .string("a")]), typecast: true)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect((body?["typecast"] as? Bool) == true)
    }

    // MARK: - OrmTable

    @Test func ormCreateDefaultOmitsTypecast() async throws {
        _ = try await ormTable().create(TypecastModel(name: "a"))
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect(body?["typecast"] == nil)
    }

    @Test func ormCreateSetIncludesTypecast() async throws {
        _ = try await ormTable().create(TypecastModel(name: "a"), typecast: true)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect((body?["typecast"] as? Bool) == true)
    }

    @Test func ormUpdateDefaultOmitsTypecast() async throws {
        // A dirty field is required for update to actually PATCH.
        let model = TypecastModel(id: "rec1", name: "old")
        model.name = "new"
        _ = try await ormTable().update(model)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect(body?["typecast"] == nil)
    }

    @Test func ormUpdateSetIncludesTypecast() async throws {
        let model = TypecastModel(id: "rec1", name: "old")
        model.name = "new"
        _ = try await ormTable().update(model, typecast: true)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect((body?["typecast"] as? Bool) == true)
    }

    @Test func ormUpsertDefaultOmitsTypecast() async throws {
        _ = try await ormTable().upsert(
            TypecastModel(name: "a"), matchFieldsToMerge: ["fldName001"])
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect(body?["typecast"] == nil)
        // Sanity: upsert body really did carry performUpsert.
        #expect(body?["performUpsert"] != nil)
    }

    @Test func ormUpsertSetIncludesTypecast() async throws {
        _ = try await ormTable().upsert(
            TypecastModel(name: "a"), matchFieldsToMerge: ["fldName001"], typecast: true)
        let body = CaptureBodyURLProtocol.capturedBody()
        #expect((body?["typecast"] as? Bool) == true)
    }
}
