import Foundation

/// Errors raised by the MyAirtable runtime. All cases are `Sendable` so they
/// can cross actor boundaries.
public enum AirtableError: Error, Sendable {
    /// Non-2xx HTTP response. `body` is the raw response body if decodable as UTF-8.
    case http(statusCode: Int, body: String?)

    /// Airtable returned a structured error envelope (`{"error": {"type": ..., "message": ...}}`).
    case api(code: String, message: String)

    /// JSON decoding failed. The wrapped error originates from `JSONDecoder`.
    case decoding(underlying: Error)

    /// A request URL could not be constructed.
    case invalidUrl

    /// `AirtableClient` was initialized without an API key or base ID.
    case missingCredentials

    /// Airtable returned 429 Too Many Requests. `retryAfter` is the `Retry-After`
    /// header value in seconds if present.
    case rateLimited(retryAfter: TimeInterval?)
}

extension AirtableError: CustomStringConvertible {
    public var description: String {
        switch self {
        case .http(let statusCode, let body):
            if let body = body, !body.isEmpty {
                return "AirtableError.http(\(statusCode)): \(body)"
            }
            return "AirtableError.http(\(statusCode))"
        case .api(let code, let message):
            return "AirtableError.api(\(code)): \(message)"
        case .decoding(let underlying):
            return "AirtableError.decoding: \(underlying)"
        case .invalidUrl:
            return "AirtableError.invalidUrl"
        case .missingCredentials:
            return "AirtableError.missingCredentials"
        case .rateLimited(let retryAfter):
            if let retryAfter = retryAfter {
                return "AirtableError.rateLimited(retryAfter: \(retryAfter)s)"
            }
            return "AirtableError.rateLimited"
        }
    }
}

extension AirtableError: Equatable {
    public static func == (lhs: AirtableError, rhs: AirtableError) -> Bool {
        switch (lhs, rhs) {
        case (.http(let l1, let l2), .http(let r1, let r2)):
            return l1 == r1 && l2 == r2
        case (.api(let l1, let l2), .api(let r1, let r2)):
            return l1 == r1 && l2 == r2
        case (.decoding, .decoding):
            // Underlying decode errors are not Equatable; treat all decoding errors as equal.
            return true
        case (.invalidUrl, .invalidUrl):
            return true
        case (.missingCredentials, .missingCredentials):
            return true
        case (.rateLimited(let l), .rateLimited(let r)):
            return l == r
        default:
            return false
        }
    }
}

/// Wire-format Airtable error envelope. Matches the shape Airtable returns on
/// non-2xx responses: `{"error": {"type": "...", "message": "..."}}` or
/// `{"error": "STRING"}` for some legacy endpoints.
struct AirtableErrorEnvelope: Decodable {
    let error: ErrorPayload

    enum ErrorPayload: Decodable {
        case structured(type: String, message: String)
        case string(String)

        init(from decoder: any Decoder) throws {
            if let container = try? decoder.singleValueContainer(),
                let raw = try? container.decode(String.self)
            {
                self = .string(raw)
                return
            }
            let container = try decoder.container(keyedBy: CodingKeys.self)
            let type = try container.decode(String.self, forKey: .type)
            let message = try container.decodeIfPresent(String.self, forKey: .message) ?? ""
            self = .structured(type: type, message: message)
        }

        enum CodingKeys: String, CodingKey {
            case type
            case message
        }
    }

    /// Convert to the public error type.
    func toAirtableError() -> AirtableError {
        switch error {
        case .structured(let type, let message):
            return .api(code: type, message: message)
        case .string(let raw):
            return .api(code: "UNKNOWN", message: raw)
        }
    }
}
