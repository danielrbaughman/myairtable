// F2.10 — Verify Fields supports dual ID/name access: IDs tried first, names
// translated via nameToId. This is the parity point with the Rust
// static/rust/struct_table.rs Fields API, and unlocks the generated
// {Table}Fields.primaryKeyId / .primaryKeyName constants.

import Foundation
import Testing

@testable import MyAirtableStatic

@Suite("Fields dual ID/name access")
struct TestFieldsDualAccess {
    // Generator-style map: field name -> field ID.
    private let nameMap: [String: String] = [
        "Primary Key": "fldPrimary",
        "Count": "fldCount",
        "Active": "fldActive",
    ]

    @Test("ID lookup returns the stored value")
    func testIdLookup() {
        var f = Fields(nameToId: nameMap)
        f.setString("fldPrimary", "hello")
        #expect(f.getString("fldPrimary") == "hello")
    }

    @Test("Name lookup translates to ID and returns the same value")
    func testNameLookup() {
        var f = Fields(nameToId: nameMap)
        f.setString("fldPrimary", "hello")
        #expect(f.getString("Primary Key") == "hello")
    }

    @Test("ID is tried first when both a name and an unrelated ID collide")
    func testIdBeatsName() {
        var f = Fields(
            [
                "fldPrimary": .string("viaId")
                // (Names are never directly stored — they translate to IDs via
                // nameToId before reaching storage.)
            ],
            nameToId: nameMap
        )
        #expect(f.getString("fldPrimary") == "viaId")
        #expect(f.getString("Primary Key") == "viaId")
    }

    @Test("Set by name stores under the translated ID, not the name itself")
    func testSetByNameTranslates() {
        var f = Fields(nameToId: nameMap)
        f.setString("Primary Key", "hello")
        #expect(f.ids == ["fldPrimary"])
        #expect(f.getString("fldPrimary") == "hello")
    }

    @Test("Unknown name without mapping stores under the raw key")
    func testUnknownName() {
        var f = Fields(nameToId: nameMap)
        f.setString("Unmapped Field", "x")
        // No nameToId entry — stored as-is.
        #expect(f.getString("Unmapped Field") == "x")
    }

    @Test("Nil set removes the entry")
    func testNilRemovesEntry() {
        var f = Fields(nameToId: nameMap)
        f.setString("Count", "42")
        #expect(f.count == 1)
        f.setString("Count", nil)
        #expect(f.count == 0)
    }

    @Test("Typed getInt handles both int and double storage")
    func testGetInt() {
        var f = Fields()
        f.setInt("x", 42)
        #expect(f.getInt("x") == 42)

        f.setDouble("y", 3.14)
        #expect(f.getInt("y") == 3)
    }

    @Test("Typed getDouble handles both int and double storage")
    func testGetDouble() {
        var f = Fields()
        f.setDouble("pi", 3.14)
        #expect(f.getDouble("pi") == 3.14)

        f.setInt("answer", 42)
        #expect(f.getDouble("answer") == 42.0)
    }

    @Test("Subscript delegates to get/set")
    func testSubscript() {
        var f = Fields(nameToId: nameMap)
        f["Primary Key"] = .string("via subscript")
        #expect(f["fldPrimary"] == .string("via subscript"))
        #expect(f["Primary Key"] == .string("via subscript"))
        f["Primary Key"] = nil
        #expect(f["fldPrimary"] == nil)
    }

    @Test("Codable round-trip preserves storage but drops nameToId")
    func testCodableRoundTrip() throws {
        var original = Fields(nameToId: nameMap)
        original.setString("Primary Key", "hello")
        original.setInt("Count", 42)

        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Fields.self, from: data)

        // Storage survives via field IDs.
        #expect(decoded.getString("fldPrimary") == "hello")
        #expect(decoded.getInt("fldCount") == 42)
        // nameToId is *not* serialized (it's generator metadata, not wire data).
        #expect(decoded.getString("Primary Key") == nil)
    }

    @Test("setStrings encodes a string array")
    func testSetStrings() {
        var f = Fields()
        f.setStrings("tags", ["a", "b", "c"])
        let arr = f.getArray("tags") ?? []
        #expect(arr.count == 3)
        #expect(arr[0] == .string("a"))
    }
}

// myairtable-hwqs — set() is ID-first like get() (parity with Kotlin PR #19 fix).
@Suite("Fields set ID-first")
struct TestFieldsSetIdFirst {
    @Test("Set is ID-first when a name and an unrelated ID collide")
    func setIdFirstOnCollision() {
        var fields = Fields(
            ["fldX": .string("by-id"), "fldY": .string("by-name")],
            nameToId: ["fldX": "fldY"]
        )
        fields.set("fldX", .string("updated"))
        #expect(fields.get("fldX") == .string("updated"))
        #expect(fields.get("fldY") == .string("by-name"))
    }

    @Test("A known field ID absent from storage is still never name-translated")
    func setKnownIdSparseStorage() {
        var fields = Fields(
            [:],
            nameToId: ["fldABC": "fldDEF", "Real Name": "fldABC"]
        )
        fields.set("fldABC", .int(1))
        #expect(fields.get("fldABC") == .int(1))
        #expect(fields.get("fldDEF") == nil)
    }
}
