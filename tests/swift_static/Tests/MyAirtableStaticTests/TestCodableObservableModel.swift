// F1 Phase 0 gate (myairtable-oa36): validate that `@Observable` coexists with
// a manually written `Codable` conformance. Swift's `@Observable` macro
// replaces stored-property backing, which breaks memberwise `Codable`
// synthesis — so every generated model must provide manual `CodingKeys`,
// `init(from:)`, and `encode(to:)`. If this prototype compiles and the
// round-trip tests pass, the generator template is safe to build on.
//
// Models mirror the shape the generator will emit:
//  - `@Observable final class` with `let` for computed fields, `var` for writable.
//  - Top-level `id` / `createdTime` (Airtable record envelope).
//  - Nested `fields` container keyed by Airtable field IDs.

import Foundation
import Observation
import Testing

@Observable
final class PrototypeModel: Codable {
    // Computed-field analogs (server-owned) — `let`, decoded only.
    let id: String?
    let createdTime: Date?

    // Writable-field analogs (user-settable) — `var`, encoded + decoded.
    var name: String?
    var count: Int?
    var isActive: Bool?

    // Top-level Airtable envelope keys.
    private enum CodingKeys: String, CodingKey {
        case id
        case createdTime
        case fields
    }

    // Nested `fields` container keyed by Airtable field IDs (stable across rename).
    private enum FieldsCodingKeys: String, CodingKey {
        case name = "fldName001"
        case count = "fldCount002"
        case isActive = "fldActive003"
    }

    init(
        id: String? = nil,
        createdTime: Date? = nil,
        name: String? = nil,
        count: Int? = nil,
        isActive: Bool? = nil
    ) {
        self.id = id
        self.createdTime = createdTime
        self.name = name
        self.count = count
        self.isActive = isActive
    }

    required init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decodeIfPresent(String.self, forKey: .id)
        self.createdTime = try c.decodeIfPresent(Date.self, forKey: .createdTime)
        if let fields = try? c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields) {
            self.name = try fields.decodeIfPresent(String.self, forKey: .name)
            self.count = try fields.decodeIfPresent(Int.self, forKey: .count)
            self.isActive = try fields.decodeIfPresent(Bool.self, forKey: .isActive)
        } else {
            self.name = nil
            self.count = nil
            self.isActive = nil
        }
    }

    func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(id, forKey: .id)
        try c.encodeIfPresent(createdTime, forKey: .createdTime)
        var fields = c.nestedContainer(keyedBy: FieldsCodingKeys.self, forKey: .fields)
        try fields.encodeIfPresent(name, forKey: .name)
        try fields.encodeIfPresent(count, forKey: .count)
        try fields.encodeIfPresent(isActive, forKey: .isActive)
    }
}

@Suite("@Observable + Codable co-existence (F1 Phase 0 gate)")
struct TestCodableObservableModel {
    @Test("Encode produces expected JSON shape")
    func testEncode() throws {
        let model = PrototypeModel(
            id: "recABC123",
            createdTime: Date(timeIntervalSince1970: 0),
            name: "Hello",
            count: 42,
            isActive: true
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(model)
        let json = String(data: data, encoding: .utf8) ?? ""
        #expect(json.contains("\"id\":\"recABC123\""))
        #expect(json.contains("\"fldName001\":\"Hello\""))
        #expect(json.contains("\"fldCount002\":42"))
        #expect(json.contains("\"fldActive003\":true"))
    }

    @Test("Decode populates all fields via nested container")
    func testDecode() throws {
        let json = """
            {
              "id": "recABC123",
              "createdTime": "2024-01-15T10:30:00Z",
              "fields": {
                "fldName001": "World",
                "fldCount002": 7,
                "fldActive003": false
              }
            }
            """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let model = try decoder.decode(PrototypeModel.self, from: Data(json.utf8))
        #expect(model.id == "recABC123")
        #expect(model.createdTime != nil)
        #expect(model.name == "World")
        #expect(model.count == 7)
        #expect(model.isActive == false)
    }

    @Test("Round-trip preserves all writable values")
    func testRoundTrip() throws {
        let original = PrototypeModel(
            id: "recXYZ",
            createdTime: nil,
            name: "Round",
            count: 100,
            isActive: true
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(original)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let decoded = try decoder.decode(PrototypeModel.self, from: data)
        #expect(decoded.id == original.id)
        #expect(decoded.name == original.name)
        #expect(decoded.count == original.count)
        #expect(decoded.isActive == original.isActive)
    }

    @Test("Missing fields decode as nil (sparse Airtable responses)")
    func testMissingFields() throws {
        let json = """
            { "id": "recEmpty", "fields": {} }
            """
        let decoder = JSONDecoder()
        let model = try decoder.decode(PrototypeModel.self, from: Data(json.utf8))
        #expect(model.id == "recEmpty")
        #expect(model.name == nil)
        #expect(model.count == nil)
        #expect(model.isActive == nil)
    }

    @Test("Entire 'fields' object missing decodes without throwing")
    func testMissingFieldsContainer() throws {
        let json = """
            { "id": "recBare" }
            """
        let decoder = JSONDecoder()
        let model = try decoder.decode(PrototypeModel.self, from: Data(json.utf8))
        #expect(model.id == "recBare")
        #expect(model.name == nil)
    }

    @Test("@Observable class still allows mutation after manual Codable")
    func testObservableMutation() {
        let model = PrototypeModel(name: "Initial")
        #expect(model.name == "Initial")
        model.name = "Changed"
        #expect(model.name == "Changed")
        model.count = 10
        #expect(model.count == 10)
    }

    @Test("`let` computed-field analog is decode-only (cannot be mutated)")
    func testComputedFieldIsLet() throws {
        let json = """
            { "id": "recConst", "createdTime": "2024-01-15T10:30:00Z", "fields": {} }
            """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let model = try decoder.decode(PrototypeModel.self, from: Data(json.utf8))
        #expect(model.id == "recConst")
        // Compile-time guarantee: `model.id = "..."` would not compile. We
        // don't enforce that here — the point is to demonstrate the shape
        // the generator will emit.
    }
}
