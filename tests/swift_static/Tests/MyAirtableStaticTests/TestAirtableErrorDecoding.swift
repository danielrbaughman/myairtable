// F2.9 — Decode real-world Airtable error response bodies into AirtableError
// via the internal AirtableErrorEnvelope. Structured form (default) and
// legacy string form both supported.

import Foundation
import Testing

@testable import MyAirtableStatic

@Suite("AirtableErrorEnvelope decoding")
struct TestAirtableErrorDecoding {
    @Test("Structured error body decodes to .api with type + message")
    func testStructuredError() throws {
        let json = """
            {
              "error": {
                "type": "NOT_FOUND",
                "message": "Record not found"
              }
            }
            """
        let envelope = try JSONDecoder().decode(
            AirtableErrorEnvelope.self,
            from: Data(json.utf8)
        )
        let err = envelope.toAirtableError()
        #expect(err == .api(code: "NOT_FOUND", message: "Record not found"))
    }

    @Test("Structured error with empty message decodes to .api with empty string")
    func testStructuredErrorEmptyMessage() throws {
        let json = """
            { "error": { "type": "INVALID_REQUEST" } }
            """
        let envelope = try JSONDecoder().decode(
            AirtableErrorEnvelope.self,
            from: Data(json.utf8)
        )
        let err = envelope.toAirtableError()
        #expect(err == .api(code: "INVALID_REQUEST", message: ""))
    }

    @Test("Legacy string-form error decodes to .api with code UNKNOWN")
    func testLegacyStringError() throws {
        let json = """
            { "error": "AUTHENTICATION_REQUIRED" }
            """
        let envelope = try JSONDecoder().decode(
            AirtableErrorEnvelope.self,
            from: Data(json.utf8)
        )
        let err = envelope.toAirtableError()
        #expect(err == .api(code: "UNKNOWN", message: "AUTHENTICATION_REQUIRED"))
    }

    @Test("Common Airtable error types decode cleanly")
    func testCommonErrorTypes() throws {
        let cases: [(String, String)] = [
            ("NOT_FOUND", "Could not find record"),
            ("INVALID_REQUEST_UNKNOWN_FIELD", "Unknown field name"),
            ("INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND", "Permission denied"),
            ("AUTHENTICATION_REQUIRED", "Not authenticated"),
            ("TABLE_NOT_FOUND", "Could not find table"),
        ]
        for (code, message) in cases {
            let json = """
                { "error": { "type": "\(code)", "message": "\(message)" } }
                """
            let env = try JSONDecoder().decode(AirtableErrorEnvelope.self, from: Data(json.utf8))
            #expect(env.toAirtableError() == .api(code: code, message: message))
        }
    }

    @Test("Malformed body throws a decoding error")
    func testMalformedBody() {
        let json = "{ \"nope\": true }"
        #expect(throws: Error.self) {
            _ = try JSONDecoder().decode(AirtableErrorEnvelope.self, from: Data(json.utf8))
        }
    }

    @Test("AirtableError description is human-readable")
    func testErrorDescription() {
        let err = AirtableError.api(code: "NOT_FOUND", message: "Could not find record")
        #expect(String(describing: err).contains("NOT_FOUND"))
        #expect(String(describing: err).contains("Could not find record"))
    }

    @Test("AirtableError.rateLimited with retry-after formats correctly")
    func testRateLimitedDescription() {
        let err = AirtableError.rateLimited(retryAfter: 30)
        #expect(String(describing: err).contains("30"))
    }

    @Test("AirtableError.http without body omits body text")
    func testHttpDescriptionNoBody() {
        let err = AirtableError.http(statusCode: 500, body: nil)
        #expect(String(describing: err).contains("500"))
    }

    @Test("AirtableError Equatable reflexive")
    func testEquatableReflexive() {
        let a = AirtableError.api(code: "X", message: "y")
        let b = AirtableError.api(code: "X", message: "y")
        #expect(a == b)
    }

    @Test("AirtableError Equatable different codes are not equal")
    func testEquatableDifferent() {
        #expect(AirtableError.invalidUrl != AirtableError.missingCredentials)
        #expect(AirtableError.http(statusCode: 404, body: nil) != AirtableError.http(statusCode: 500, body: nil))
    }
}
