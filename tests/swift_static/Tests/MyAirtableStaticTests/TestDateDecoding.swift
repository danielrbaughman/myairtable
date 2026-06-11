// myairtable-s9ac — Airtable returns date-only fields as "YYYY-MM-DD", which
// Foundation's .iso8601 strategy rejects. The .airtable strategy (Types.swift)
// must accept all three wire shapes: fractional ISO 8601, plain ISO 8601, and
// date-only.

import Foundation
import Testing

@testable import MyAirtableStatic

@Suite("Airtable date decoding")
struct TestDateDecoding {
    private struct Box: Codable {
        let date: Date
    }

    private func decode(_ raw: String) throws -> Date {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .airtable
        let json = #"{"date": "\#(raw)"}"#
        return try decoder.decode(Box.self, from: Data(json.utf8)).date
    }

    @Test("Full ISO 8601 with fractional seconds decodes")
    func testFractionalIso() throws {
        let date = try decode("2024-01-15T10:30:00.000Z")
        #expect(date.timeIntervalSince1970 == 1_705_314_600)
    }

    @Test("ISO 8601 without fractional seconds decodes")
    func testPlainIso() throws {
        let date = try decode("2024-01-15T10:30:00Z")
        #expect(date.timeIntervalSince1970 == 1_705_314_600)
    }

    @Test("Date-only YYYY-MM-DD decodes as UTC midnight")
    func testDateOnly() throws {
        let date = try decode("2024-01-15")
        #expect(date.timeIntervalSince1970 == 1_705_276_800)
    }

    @Test("Garbage date string throws DecodingError")
    func testGarbageThrows() {
        #expect(throws: DecodingError.self) {
            _ = try decode("not-a-date")
        }
    }

    @Test("AirtableDateParser parses all supported shapes")
    func testParserShapes() {
        #expect(AirtableDateParser.parse("2024-01-15T10:30:00.123Z") != nil)
        #expect(AirtableDateParser.parse("2024-01-15T10:30:00+02:00") != nil)
        #expect(AirtableDateParser.parse("2024-01-15") != nil)
        #expect(AirtableDateParser.parse("01/15/2024") == nil)
        #expect(AirtableDateParser.parse("") == nil)
    }
}
