// myairtable-6q37.8 — the local `copy()` verb on generated ORM models (Swift target).
//
// `record.copy()` returns a detached, unsaved model you mutate and hand to
// `airtable.<table>.create(_:)`. It is the local half of the table's `duplicate(_:)`:
// duplicate == fetch + copy + create, so copy is the part that does no I/O at all —
// which is why, unlike duplicate, it is 100% hermetically testable.
//
// The generator emits `copy()` and its `private init(_copyOf:)` INSIDE each
// `{Table}Model` class, because computed fields are `public let` and only an
// initializer can seed a `let`. This file therefore carries a stand-in model built to
// the exact shape `swift.py` emits (the package compiles only the static runtime, so
// the stand-in is also what pins the emitted call shapes — if the generated body stops
// compiling against the runtime, this file stops compiling too).
//
// Covered here: the detach (id / createdTime / snapshot cleared, client kept), computed
// values readable on the copy but ABSENT from the create payload, writable attachments
// projected to {url, filename} while a computed attachment-shaped cell keeps its full
// metadata, no shared state with the source, the source left untouched, and zero
// requests issued.

import Foundation
import Observation
import Testing

@testable import MyAirtableStatic

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

// =============================================================================
// MARK: - Stand-in model (mirrors swift.py's emitted shape exactly)
// =============================================================================

/// Field ids match the generator's `FieldsCodingKeys` convention (`fld…`).
///
///   writable: fld001 name, fld002 photos, fld004 count, fld005 tags, fld006 links
///   computed: fld007 myFormula, fld008 auto, fld009 lookupPhotos
///
/// `fld009` is the interesting one: a lookup of an attachment field renders as
/// `VecOrValue<MaybeSpecialOrError<AirtableAttachment>>`, i.e. the *same* attachment
/// struct as the writable `fld002` — so "project attachments" has to be decided by the
/// writable/computed split, not by the value's shape.
@Observable
final class CopyPayloadModel: AirtableModel {
    static let tableId: String = "tblCopy001"

    // MARK: - Identity
    let id: RecordId?
    let createdTime: Date?

    // MARK: - Computed fields (server-owned)
    let myFormula: MaybeSpecialOrError<Double>?
    let auto: MaybeSpecialOrError<Int>?
    let lookupPhotos: VecOrValue<MaybeSpecialOrError<AirtableAttachment>>?

    // MARK: - Writable fields
    var name: String?
    var photos: [AirtableAttachment]?
    var count: Double?
    var tags: AirtableJSONValue?
    var links: [RecordId]?

    // MARK: - Dirty tracking
    @ObservationIgnored
    private var _snapshot: [String: AirtableJSONValue] = [:]

    @ObservationIgnored
    var _attachedClient: AirtableClient?

    // MARK: - Construction
    /// The generator's designated initializer: writable fields only, everything
    /// server-owned nil, and deliberately NO `takeSnapshot()` — a hand-built model is
    /// fully dirty because all of it has to be inserted.
    init(
        name: String? = nil,
        photos: [AirtableAttachment]? = nil,
        count: Double? = nil,
        tags: AirtableJSONValue? = nil,
        links: [RecordId]? = nil
    ) {
        self.id = nil
        self.createdTime = nil
        self.myFormula = nil
        self.auto = nil
        self.lookupPhotos = nil
        self.name = name
        self.photos = photos
        self.count = count
        self.tags = tags
        self.links = links
    }

    // MARK: - Codable
    private enum CodingKeys: String, CodingKey {
        case id
        case createdTime
        case fields
    }

    private enum FieldsCodingKeys: String, CodingKey {
        case name = "fld001"
        case photos = "fld002"
        case count = "fld004"
        case tags = "fld005"
        case links = "fld006"
        case myFormula = "fld007"
        case auto = "fld008"
        case lookupPhotos = "fld009"
    }

    required init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decodeIfPresent(String.self, forKey: .id)
        self.createdTime = try c.decodeIfPresent(Date.self, forKey: .createdTime)
        if let fields = try? c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields) {
            self.name = try fields.decodeIfPresent(String.self, forKey: .name)
            self.photos = try fields.decodeIfPresent([AirtableAttachment].self, forKey: .photos)
            self.count = try fields.decodeIfPresent(Double.self, forKey: .count)
            self.tags = try fields.decodeIfPresent(AirtableJSONValue.self, forKey: .tags)
            self.links = try fields.decodeIfPresent([RecordId].self, forKey: .links)
            self.myFormula = try fields.decodeIfPresent(MaybeSpecialOrError<Double>.self, forKey: .myFormula)
            self.auto = try fields.decodeIfPresent(MaybeSpecialOrError<Int>.self, forKey: .auto)
            self.lookupPhotos = try fields.decodeIfPresent(
                VecOrValue<MaybeSpecialOrError<AirtableAttachment>>.self,
                forKey: .lookupPhotos
            )
        } else {
            self.name = nil
            self.photos = nil
            self.count = nil
            self.tags = nil
            self.links = nil
            self.myFormula = nil
            self.auto = nil
            self.lookupPhotos = nil
        }
        self.takeSnapshot()
    }

    /// Writable fields ONLY. This is the target's computed-field filter: `toRecord()`
    /// round-trips through this encoder, and `OrmTable.create(_:)` sends `toRecord()`
    /// verbatim, so a computed value physically cannot reach a POST body.
    func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(id, forKey: .id)
        try c.encodeIfPresent(createdTime, forKey: .createdTime)
        var fields = c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields)
        try fields.encodeIfPresent(name, forKey: .name)
        try fields.encodeIfPresent(photos, forKey: .photos)
        try fields.encodeIfPresent(count, forKey: .count)
        try fields.encodeIfPresent(tags, forKey: .tags)
        try fields.encodeIfPresent(links, forKey: .links)
    }

    // MARK: - AirtableModel
    func toRecord() -> [String: AirtableJSONValue] {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(self) else { return [:] }
        struct Envelope: Decodable { let fields: [String: AirtableJSONValue] }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let env = try? decoder.decode(Envelope.self, from: data) else { return [:] }
        return env.fields
    }

    func takeSnapshot() {
        self._snapshot = toRecord()
    }

    func dirtyFields() -> [String: AirtableJSONValue] {
        let current = toRecord()
        let writableIds: Set<String> = ["fld001", "fld002", "fld004", "fld005", "fld006"]
        var dirty: [String: AirtableJSONValue] = [:]
        for id in writableIds {
            if current[id] != _snapshot[id] { dirty[id] = current[id] ?? .null }
        }
        return dirty
    }

    // MARK: - copy
    func copy() -> CopyPayloadModel {
        return CopyPayloadModel(_copyOf: self)
    }

    private init(_copyOf source: CopyPayloadModel) {
        self.id = nil
        self.createdTime = nil
        self.myFormula = source.myFormula
        self.auto = source.auto
        self.lookupPhotos = source.lookupPhotos
        self.name = source.name
        self.photos = projectAttachmentsForCopy(source.photos)
        self.count = source.count
        self.tags = source.tags
        self.links = source.links
        self._attachedClient = source._attachedClient
    }
}

// =============================================================================
// MARK: - Fixtures
// =============================================================================

/// A record as Airtable actually returns it: a real id and createdTime, attachments
/// carrying the full server metadata, and computed cells populated.
private let sourceJSON = """
    {
      "id": "recSOURCE0001",
      "createdTime": "2024-01-15T10:30:00Z",
      "fields": {
        "fld001": "Original name",
        "fld002": [
          {
            "id": "attWRITABLE01",
            "url": "https://example.com/a.png",
            "filename": "a.png",
            "size": 1234,
            "type": "image/png",
            "thumbnails": { "small": { "url": "https://example.com/a-sm.png", "width": 36, "height": 36 } }
          },
          {
            "id": "attWRITABLE02",
            "url": "https://example.com/b.pdf",
            "filename": "b.pdf",
            "size": 999,
            "type": "application/pdf"
          }
        ],
        "fld004": 42,
        "fld005": ["red", "blue"],
        "fld006": ["recLINKED001", "recLINKED002"],
        "fld007": 3.5,
        "fld008": 17,
        "fld009": [
          {
            "id": "attCOMPUTED01",
            "url": "https://example.com/c.png",
            "filename": "c.png",
            "size": 555,
            "type": "image/png",
            "thumbnails": { "large": { "url": "https://example.com/c-lg.png", "width": 512, "height": 512 } }
          }
        ]
      }
    }
    """

private func decodeSource(_ json: String = sourceJSON) throws -> CopyPayloadModel {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .airtable
    return try decoder.decode(CopyPayloadModel.self, from: Data(json.utf8))
}

/// Counts every request that reaches the transport and answers with a canned create
/// envelope. `copy()` must never make one appear.
private final class CountingURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requestCount = 0
    nonisolated(unsafe) static var lastBody: [String: Any]?
    private static let lock = NSLock()

    static func reset() {
        lock.lock()
        requestCount = 0
        lastBody = nil
        lock.unlock()
    }

    static func snapshot() -> (count: Int, body: [String: Any]?) {
        lock.lock()
        defer { lock.unlock() }
        return (requestCount, lastBody)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        // URLSession usually moves `httpBody` into `httpBodyStream` before a
        // URLProtocol sees it, so drain the stream when the direct body is nil.
        var payload = request.httpBody
        if payload == nil, let stream = request.httpBodyStream {
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
            payload = collected
        }

        Self.lock.lock()
        Self.requestCount += 1
        if let payload, let obj = try? JSONSerialization.jsonObject(with: payload),
            let dict = obj as? [String: Any]
        {
            Self.lastBody = dict
        }
        Self.lock.unlock()

        let body = Data(
            #"{"records": [{"id": "recNEW0001", "createdTime": "2024-02-02T00:00:00Z", "fields": {"fld001": "Original name"}}]}"#
                .utf8
        )
        let response = HTTPURLResponse(
            url: request.url!,
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

private func makeCountingClient() -> AirtableClient {
    CountingURLProtocol.reset()
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CountingURLProtocol.self]
    return AirtableClient(baseId: "appCopy", apiKey: "key", session: URLSession(configuration: config))
}

// =============================================================================
// MARK: - The detach
// =============================================================================

@Suite("copy() detaches the record's identity")
struct TestCopyDetach {
    @Test("id and createdTime are cleared")
    func clearsIdentity() throws {
        let source = try decodeSource()
        let copy = source.copy()

        #expect(source.id == "recSOURCE0001")
        #expect(source.createdTime != nil)
        #expect(copy.id == nil)
        #expect(copy.createdTime == nil)
    }

    @Test("the copy reports itself as new, so it inserts rather than updating")
    func copyIsNew() throws {
        let source = try decodeSource()
        let copy = source.copy()

        #expect(source.isNew == false)
        #expect(copy.isNew == true)
    }

    @Test("save() on a copy refuses — a copy is inserted with create(_:), never PATCHed")
    func saveOnCopyThrows() async throws {
        let source = try decodeSource()
        source._attachedClient = makeCountingClient()
        let copy = source.copy()

        // The load-bearing failure this guards: had `id` survived the copy, `save()`
        // would happily PATCH the SOURCE row instead of inserting a new record.
        await #expect(throws: AirtableError.self) { _ = try await copy.save() }
        #expect(CountingURLProtocol.snapshot().count == 0)
    }

    @Test("the snapshot is NOT carried: the copy is fully dirty, the source is clean")
    func snapshotIsReset() throws {
        let source = try decodeSource()
        let copy = source.copy()

        // A decoded source took a snapshot, so nothing on it reads as changed.
        #expect(source.dirtyFields().isEmpty)

        // The copy's snapshot is empty, so every populated writable cell is dirty.
        // If the snapshot HAD been carried, this would be empty — and the runtime's
        // own trap: an "unchanged" record inserted as {"fields":{}}, a blank row.
        let dirty = copy.dirtyFields()
        #expect(Set(dirty.keys) == ["fld001", "fld002", "fld004", "fld005", "fld006"])
    }

    @Test("the attached client is KEPT, so copy.save()/create() need no table re-threading")
    func clientIsRetained() throws {
        let client = makeCountingClient()
        let source = try decodeSource()
        source._attachedClient = client
        let copy = source.copy()

        #expect(copy._attachedClient != nil)
        #expect(copy._attachedClient === client)
    }

    @Test("a copy of an unattached model stays unattached")
    func clientStaysNilWhenSourceHasNone() throws {
        let source = try decodeSource()
        #expect(source._attachedClient == nil)
        #expect(source.copy()._attachedClient == nil)
    }

    @Test("copy of a copy is still detached and still carries the values")
    func copyOfACopy() throws {
        let source = try decodeSource()
        source._attachedClient = makeCountingClient()
        let second = source.copy().copy()

        #expect(second.id == nil)
        #expect(second.createdTime == nil)
        #expect(second.isNew)
        #expect(second.name == "Original name")
        #expect(second._attachedClient === source._attachedClient)
        // Already projected once; projecting again is a no-op, not a loss.
        #expect(second.photos?.count == 2)
        #expect(second.photos?.first?.url == "https://example.com/a.png")
        #expect(second.photos?.first?.id == nil)
    }
}

// =============================================================================
// MARK: - Values carried
// =============================================================================

@Suite("copy() carries every cell value, computed ones included")
struct TestCopyCarriesValues {
    @Test("writable values are carried verbatim")
    func writableValuesCarried() throws {
        let source = try decodeSource()
        let copy = source.copy()

        #expect(copy.name == "Original name")
        #expect(copy.count == 42)
        #expect(copy.tags == .array([.string("red"), .string("blue")]))
        #expect(copy.links == ["recLINKED001", "recLINKED002"])
    }

    @Test("computed values are readable on the copy, so it reads like its source")
    func computedValuesCarried() throws {
        let source = try decodeSource()
        let copy = source.copy()

        #expect(copy.myFormula?.value == 3.5)
        #expect(copy.auto?.value == 17)
        #expect(copy.lookupPhotos?.values.first?.value?.filename == "c.png")
    }

    @Test("special / error computed values survive the copy unflattened")
    func specialAndErrorComputedValuesCarried() throws {
        let json = """
            {
              "id": "recSPECIAL01",
              "fields": { "fld007": {"specialValue": "Infinity"}, "fld008": {"error": "#ERROR!"} }
            }
            """
        let copy = try decodeSource(json).copy()

        #expect(copy.myFormula?.special == SpecialNumber("Infinity"))
        #expect(copy.auto?.errorValue == ErrorValue("#ERROR!"))
    }

    @Test("computed values are ABSENT from the create payload")
    func computedValuesNeverReachTheWire() throws {
        let source = try decodeSource()
        let copy = source.copy()
        let payload = copy.toRecord()

        // Readable on the model…
        #expect(copy.myFormula != nil)
        #expect(copy.auto != nil)
        #expect(copy.lookupPhotos != nil)
        // …but never serialized. This is what makes carrying them safe: Airtable
        // rejects a computed field in a create body.
        #expect(payload["fld007"] == nil)
        #expect(payload["fld008"] == nil)
        #expect(payload["fld009"] == nil)
        #expect(Set(payload.keys) == ["fld001", "fld002", "fld004", "fld005", "fld006"])
    }

    @Test("links are carried as-is — Airtable links are many-to-many")
    func linksCarriedAsIs() throws {
        let source = try decodeSource()
        let copy = source.copy()

        #expect(copy.toRecord()["fld006"] == .array([.string("recLINKED001"), .string("recLINKED002")]))
        // The source's own links are untouched: the copy is ADDED alongside it on the
        // far side of the link, it does not steal the link.
        #expect(source.links == ["recLINKED001", "recLINKED002"])
    }

    @Test("a sparse record copies as sparse — absent cells stay absent, not empty")
    func sparseRecordStaysSparse() throws {
        let copy = try decodeSource(#"{"id": "recSPARSE01", "fields": {"fld001": "only a name"}}"#).copy()

        #expect(copy.name == "only a name")
        #expect(copy.photos == nil)
        #expect(copy.links == nil)
        #expect(copy.toRecord().keys.sorted() == ["fld001"])
    }
}

// =============================================================================
// MARK: - Attachment projection
// =============================================================================

@Suite("copy() projects writable attachments, and only writable ones")
struct TestCopyAttachmentProjection {
    @Test("writable attachment cells keep only url + filename on the model")
    func writableAttachmentsProjectedOnModel() throws {
        let copy = try decodeSource().copy()
        let photos = try #require(copy.photos)

        #expect(photos.count == 2)
        for photo in photos {
            #expect(photo.id == nil)
            #expect(photo.size == nil)
            #expect(photo.type == nil)
            #expect(photo.thumbnails == nil)
        }
        #expect(photos[0].url == "https://example.com/a.png")
        #expect(photos[0].filename == "a.png")
        #expect(photos[1].url == "https://example.com/b.pdf")
        #expect(photos[1].filename == "b.pdf")
    }

    @Test("the serialized cell is EXACTLY {url, filename}")
    func writableAttachmentsSerializeToUrlAndFilenameOnly() throws {
        let copy = try decodeSource().copy()
        guard case .array(let items)? = copy.toRecord()["fld002"] else {
            Issue.record("fld002 did not serialize as an array")
            return
        }
        #expect(items.count == 2)
        for item in items {
            guard case .object(let object) = item else {
                Issue.record("attachment did not serialize as an object")
                continue
            }
            // Echoing an `id` back on create is INVALID_ATTACHMENT_OBJECT, and
            // OrmTable.create(_:) does NOT project — only duplicate(_:) does. So this
            // has to already be true by the time copy() hands the model back.
            #expect(object.keys.sorted() == ["filename", "url"])
        }
    }

    @Test("a computed attachment-shaped cell keeps its full metadata")
    func computedAttachmentCellKeepsMetadata() throws {
        let copy = try decodeSource().copy()
        let lookup = try #require(copy.lookupPhotos?.values.first?.value)

        // Same struct as the writable cell, deliberately NOT projected: a lookup is
        // never written back, so stripping it would lose fidelity for nothing.
        #expect(lookup.id == "attCOMPUTED01")
        #expect(lookup.size == 555)
        #expect(lookup.type == "image/png")
        #expect(lookup.thumbnails?.large?.url == "https://example.com/c-lg.png")
    }

    @Test("the SOURCE's attachments are never projected in place")
    func sourceAttachmentsUnprojected() throws {
        let source = try decodeSource()
        _ = source.copy()

        #expect(source.photos?.first?.id == "attWRITABLE01")
        #expect(source.photos?.first?.size == 1234)
        #expect(source.photos?.first?.thumbnails?.small?.width == 36)
    }

    @Test("nil stays nil, empty stays empty")
    func absentAndEmptyAttachmentCellsAreDistinct() throws {
        let absent = try decodeSource(#"{"id": "recA", "fields": {}}"#).copy()
        #expect(absent.photos == nil)
        #expect(absent.toRecord()["fld002"] == nil)

        // An empty list is not "unset" — on the wire it CLEARS the cell — so it must
        // survive as an empty list rather than collapsing to nil.
        let empty = try decodeSource(#"{"id": "recB", "fields": {"fld002": []}}"#).copy()
        #expect(empty.photos == [])
        #expect(empty.toRecord()["fld002"] == .array([]))
    }

    @Test("projectAttachmentsForCopy overloads: list, scalar, VecOrValue")
    func projectionHelperOverloads() throws {
        let full = AirtableAttachment(
            id: "att1",
            url: "https://example.com/x.png",
            filename: "x.png",
            size: 10,
            type: "image/png",
            thumbnails: nil
        )

        // The list overload — the shape `multipleAttachments` renders as.
        let list = projectAttachmentsForCopy([full])
        #expect(list == [AirtableAttachment(url: "https://example.com/x.png", filename: "x.png")])
        #expect(projectAttachmentsForCopy(nil as [AirtableAttachment]?) == nil)

        // The scalar overload.
        #expect(projectAttachmentsForCopy(full)?.id == nil)
        #expect(projectAttachmentsForCopy(full)?.url == "https://example.com/x.png")
        #expect(projectAttachmentsForCopy(nil as AirtableAttachment?) == nil)

        // The VecOrValue overload — unreachable from today's schema, but the emission
        // rule is type-driven, so it has to exist and has to descend through both cases.
        #expect(projectAttachmentsForCopy(VecOrValue<AirtableAttachment>.single(full))?.single?.id == nil)
        let projected = projectAttachmentsForCopy(VecOrValue<AirtableAttachment>.multiple([full, nil]))
        let items = try #require(projected?.multiple)
        #expect(items.count == 2)
        #expect(items[0]?.id == nil)
        #expect(items[0]?.filename == "x.png")
        // A null element of a lookup array stays null rather than becoming an empty
        // attachment — Airtable puts one there when the linked record has no value.
        #expect(items[1] == nil)
        #expect(projectAttachmentsForCopy(nil as VecOrValue<AirtableAttachment>?) == nil)
    }
}

// =============================================================================
// MARK: - Isolation from the source
// =============================================================================

@Suite("the copy shares no state with its source")
struct TestCopyIsolation {
    @Test("mutating the copy's collections leaves the source alone")
    func mutatingCopyDoesNotTouchSource() throws {
        let source = try decodeSource()
        let copy = source.copy()

        copy.name = "Changed"
        copy.count = 99
        copy.links?.append("recLINKED003")
        copy.photos?.removeAll()
        copy.tags = .array([.string("green")])

        #expect(source.name == "Original name")
        #expect(source.count == 42)
        #expect(source.links == ["recLINKED001", "recLINKED002"])
        #expect(source.photos?.count == 2)
        #expect(source.tags == .array([.string("red"), .string("blue")]))
    }

    @Test("mutating the source leaves an already-taken copy alone")
    func mutatingSourceDoesNotTouchCopy() throws {
        let source = try decodeSource()
        let copy = source.copy()

        source.name = "Renamed after the copy"
        source.links = []
        source.photos = nil

        #expect(copy.name == "Original name")
        #expect(copy.links == ["recLINKED001", "recLINKED002"])
        #expect(copy.photos?.count == 2)
    }

    @Test("the source is byte-for-byte untouched by copy()")
    func sourceIsCompletelyUntouched() throws {
        let source = try decodeSource()
        let before = source.toRecord()
        let beforeId = source.id
        let beforeCreated = source.createdTime

        _ = source.copy()

        #expect(source.toRecord() == before)
        #expect(source.id == beforeId)
        #expect(source.createdTime == beforeCreated)
        #expect(source.dirtyFields().isEmpty)
        #expect(source.myFormula?.value == 3.5)
    }
}

// =============================================================================
// MARK: - Zero I/O, and what the insert actually POSTs
// =============================================================================

// Serialized: the URLProtocol stub keeps its counters in shared static state.
@Suite("copy() performs no I/O and inserts cleanly", .serialized)
struct TestCopyPerformsNoIO {
    @Test("copy() issues no request at all, even on an attached model")
    func copyIssuesNoRequests() throws {
        let source = try decodeSource()
        source._attachedClient = makeCountingClient()

        let copy = source.copy()
        _ = copy.toRecord()
        _ = copy.dirtyFields()

        // The whole difference from duplicate(_:), which re-reads the source first.
        #expect(CountingURLProtocol.snapshot().count == 0)
    }

    @Test("creating a copy POSTs the projected writable set and no record id")
    func creatingACopyPostsAnInsert() async throws {
        let client = makeCountingClient()
        let source = try decodeSource()
        source._attachedClient = client
        let copy = source.copy()
        copy.name = "Copy of the original"

        let table = OrmTable<CopyPayloadModel>(tableId: CopyPayloadModel.tableId, client: client)
        _ = try await table.create(copy)

        let (count, body) = CountingURLProtocol.snapshot()
        #expect(count == 1)

        let records = try #require(body?["records"] as? [[String: Any]])
        #expect(records.count == 1)
        // No id anywhere: this is an insert, not an update of the source.
        #expect(records[0]["id"] == nil)

        let fields = try #require(records[0]["fields"] as? [String: Any])
        #expect(fields["fld001"] as? String == "Copy of the original")
        // Computed cells never made it into the body.
        #expect(fields["fld007"] == nil)
        #expect(fields["fld008"] == nil)
        #expect(fields["fld009"] == nil)

        let attachments = try #require(fields["fld002"] as? [[String: Any]])
        #expect(attachments.count == 2)
        #expect(attachments[0].keys.sorted() == ["filename", "url"])
        #expect(attachments[0]["url"] as? String == "https://example.com/a.png")
    }
}
