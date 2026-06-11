// myairtable-ii6y — Computed-field error / special-value decoding. Parity with
// tests/test_rust_static.rs (special/error/VecOrValue cases) and
// myairtable-tests/rust/tests/test_special_error_deser.rs.
//
// Airtable returns `{"specialValue": "NaN"}` / `{"error": "#ERROR!"}` objects
// for formula / rollup / lookup fields whose computation is non-finite or
// fails. Object forms must decode; array forms must NOT (regression: lookup
// arrays like ["Lab Name"] must never collapse into Special/Error).

import Foundation
import Testing

@testable import MyAirtableStatic

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try JSONDecoder().decode(T.self, from: Data(json.utf8))
}

@Suite("Special / error value decoding")
struct TestSpecialErrorDecoding {
    // MARK: - SpecialNumber

    @Test func specialNumberAcceptsObjectForm() throws {
        let v = try decode(SpecialNumber.self, #"{"specialValue":"NaN"}"#)
        #expect(v.specialValue == "NaN")
        let inf = try decode(SpecialNumber.self, #"{"specialValue":"Infinity"}"#)
        #expect(inf.specialValue == "Infinity")
    }

    @Test func specialNumberRejectsArrayForm() {
        #expect(throws: (any Error).self) {
            _ = try decode(SpecialNumber.self, #"["NaN"]"#)
        }
    }

    // MARK: - ErrorValue

    @Test func errorValueAcceptsObjectForm() throws {
        let v = try decode(ErrorValue.self, ##"{"error":"#ERROR!"}"##)
        #expect(v.error == "#ERROR!")
    }

    @Test func errorValueRejectsArrayForm() {
        #expect(throws: (any Error).self) {
            _ = try decode(ErrorValue.self, ##"["#ERROR!"]"##)
        }
    }

    // MARK: - MaybeSpecialOrError

    @Test func maybeDecodesValue() throws {
        let v = try decode(MaybeSpecialOrError<Double>.self, "42.5")
        #expect(v == .value(42.5))
    }

    @Test func maybeDecodesSpecial() throws {
        let v = try decode(MaybeSpecialOrError<Double>.self, #"{"specialValue":"NaN"}"#)
        #expect(v == .special(SpecialNumber("NaN")))
    }

    @Test func maybeDecodesError() throws {
        let v = try decode(MaybeSpecialOrError<Double>.self, ##"{"error":"#ERROR!"}"##)
        #expect(v == .error(ErrorValue("#ERROR!")))
    }

    @Test func maybeStringParsesPlainString() throws {
        let v = try decode(MaybeSpecialOrError<String>.self, #""Stukenholtz""#)
        #expect(v.value == "Stukenholtz")
    }

    @Test func maybeStringRejectsLookupArray() {
        // Regression: ["Stukenholtz"] must not accidentally decode as Special.
        #expect(throws: (any Error).self) {
            _ = try decode(MaybeSpecialOrError<String>.self, #"["Stukenholtz"]"#)
        }
    }

    @Test func maybeHelpers() {
        let v = MaybeSpecialOrError<Int>.value(42)
        #expect(v.isValue)
        #expect(v.value == 42)
        #expect(!v.isSpecial)
        #expect(!v.isError)

        let e = MaybeSpecialOrError<Int>.error(ErrorValue("#ERROR!"))
        #expect(e.isError)
        #expect(e.value == nil)
        #expect(e.errorValue?.error == "#ERROR!")

        let s = MaybeSpecialOrError<Int>.special(SpecialNumber("NaN"))
        #expect(s.isSpecial)
        #expect(s.special?.specialValue == "NaN")
    }

    // MARK: - VecOrValue

    @Test func vecOrValueSingle() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<String>>.self, #""hello""#)
        #expect(v.single?.value == "hello")
    }

    @Test func vecOrValueMultiple() throws {
        let v = try decode(
            VecOrValue<MaybeSpecialOrError<String>>.self, #"["Stukenholtz Laboratory Inc"]"#)
        #expect(v.multiple?.count == 1)
        #expect(v.values.compactMap(\.value) == ["Stukenholtz Laboratory Inc"])
    }

    @Test func vecOrValueNullableItemsPreserved() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<String>>.self, #"["a", null, "b"]"#)
        guard let items = v.multiple else {
            Issue.record("expected multiple")
            return
        }
        #expect(items.count == 3)
        #expect(items[1] == nil)
    }

    @Test func vecOrValueAllNulls() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<String>>.self, "[null, null]")
        #expect(v.multiple?.count == 2)
        #expect(v.values.isEmpty)
    }

    @Test func vecOrValueEmpty() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<String>>.self, "[]")
        #expect(v.multiple?.isEmpty == true)
    }

    @Test func vecOrValueSpecialNumberObject() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<Double>>.self, #"{"specialValue":"NaN"}"#)
        #expect(v.single?.special?.specialValue == "NaN")
    }

    @Test func vecOrValueErrorValueObject() throws {
        let v = try decode(VecOrValue<MaybeSpecialOrError<Double>>.self, ##"{"error":"#ERROR!"}"##)
        #expect(v.single?.errorValue?.error == "#ERROR!")
    }

    @Test func vecOrValueMixedArray() throws {
        let json = ##"[1, {"specialValue":"NaN"}, {"error":"#ERROR!"}, null]"##
        let v = try decode(VecOrValue<MaybeSpecialOrError<Int>>.self, json)
        guard let items = v.multiple else {
            Issue.record("expected multiple")
            return
        }
        #expect(items.count == 4)
        #expect(items[0]?.value == 1)
        #expect(items[1]?.special?.specialValue == "NaN")
        #expect(items[2]?.errorValue?.error == "#ERROR!")
        #expect(items[3] == nil)
    }

    // MARK: - Round-trips

    @Test func specialNumberRoundTrip() throws {
        let original = SpecialNumber("NaN")
        let json = String(data: try JSONEncoder().encode(original), encoding: .utf8)!
        #expect(json == #"{"specialValue":"NaN"}"#)
        #expect(try decode(SpecialNumber.self, json) == original)
    }

    @Test func maybeEncodesUntagged() throws {
        let v = MaybeSpecialOrError<Int>.value(7)
        #expect(String(data: try JSONEncoder().encode(v), encoding: .utf8) == "7")
        let e = MaybeSpecialOrError<Int>.error(ErrorValue("#ERROR!"))
        #expect(
            String(data: try JSONEncoder().encode(e), encoding: .utf8) == ##"{"error":"#ERROR!"}"##)
    }

    @Test func vecOrValueSerializesMultipleWithNulls() throws {
        let v = VecOrValue<MaybeSpecialOrError<String>>.multiple([.value("a"), nil])
        let json = String(data: try JSONEncoder().encode(v), encoding: .utf8)!
        #expect(json == #"["a",null]"#)
    }
}
