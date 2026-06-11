import Foundation

/// Airtable record IDs are opaque strings like `recXXXXXXXXXXXXXX`. Alias to
/// `String` for ergonomics; using the alias consistently documents intent at
/// call sites and in generated code.
public typealias RecordId = String

/// Sort direction for Airtable list queries.
public enum SortDirection: String, Codable, Sendable {
    case asc
    case desc
}

/// A single sort clause. Airtable supports multiple sort clauses per query
/// and applies them left-to-right.
public struct Sort: Sendable, Equatable {
    public let field: String
    public let direction: SortDirection

    public init(field: String, direction: SortDirection = .asc) {
        self.field = field
        self.direction = direction
    }
}

/// Airtable attachment (file/image) as returned in field values.
public struct AirtableAttachment: Codable, Sendable, Equatable {
    public let id: String?
    public let url: String?
    public let filename: String?
    public let size: Int?
    public let type: String?
    public let thumbnails: AirtableThumbnails?

    public init(
        id: String? = nil,
        url: String? = nil,
        filename: String? = nil,
        size: Int? = nil,
        type: String? = nil,
        thumbnails: AirtableThumbnails? = nil
    ) {
        self.id = id
        self.url = url
        self.filename = filename
        self.size = size
        self.type = type
        self.thumbnails = thumbnails
    }
}

/// Attachment thumbnail variants (`small`, `large`, `full`).
public struct AirtableThumbnails: Codable, Sendable, Equatable {
    public let small: Thumbnail?
    public let large: Thumbnail?
    public let full: Thumbnail?

    public struct Thumbnail: Codable, Sendable, Equatable {
        public let url: String
        public let width: Int?
        public let height: Int?
    }
}

/// Airtable collaborator (user/account).
public struct AirtableCollaborator: Codable, Sendable, Equatable {
    public let id: String
    public let email: String?
    public let name: String?
    public let profilePicUrl: String?

    public init(
        id: String,
        email: String? = nil,
        name: String? = nil,
        profilePicUrl: String? = nil
    ) {
        self.id = id
        self.email = email
        self.name = name
        self.profilePicUrl = profilePicUrl
    }
}

/// Airtable button field — read-only reference to a button click action.
public struct AirtableButton: Codable, Sendable, Equatable {
    public let label: String?
    public let url: String?
}

/// Wrapping envelope for an Airtable record as returned by the API:
/// `{"id": "recXXX", "createdTime": "2024-...", "fields": {...}}`.
///
/// The generated `{Table}Model` classes decode themselves directly from this
/// shape via manual `init(from:)`. This helper is for raw record APIs
/// (e.g., `DictTable` which returns `[String: Any]` fields).
public struct AirtableRecord<Fields: Codable & Sendable>: Codable, Sendable {
    public let id: RecordId
    public let createdTime: Date?
    public let fields: Fields

    public init(id: RecordId, createdTime: Date? = nil, fields: Fields) {
        self.id = id
        self.createdTime = createdTime
        self.fields = fields
    }
}

/// A value that can be either a single `T` or a `[T]` — decoded from Airtable
/// responses where the cardinality of lookup/rollup fields can't be determined
/// from metadata alone. Equivalent to the Rust target's `VecOrValue<T>`.
public enum VecOrValue<T: Codable & Sendable>: Codable, Sendable {
    case single(T)
    case multiple([T])

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let arr = try? container.decode([T].self) {
            self = .multiple(arr)
        } else {
            self = .single(try container.decode(T.self))
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .single(let v): try container.encode(v)
        case .multiple(let v): try container.encode(v)
        }
    }

    /// Flatten to `[T]` regardless of encoding.
    public var values: [T] {
        switch self {
        case .single(let v): return [v]
        case .multiple(let v): return v
        }
    }
}

/// A type-erased JSON value used where Airtable's schema doesn't constrain a
/// field's shape (e.g., `UNKNOWN` fields, raw `DictTable` values). Codable and
/// Sendable so it can flow through strict-concurrency code paths.
public enum AirtableJSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([AirtableJSONValue])
    case object([String: AirtableJSONValue])

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Int.self) {
            self = .int(v)
        } else if let v = try? container.decode(Double.self) {
            self = .double(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([AirtableJSONValue].self) {
            self = .array(v)
        } else if let v = try? container.decode([String: AirtableJSONValue].self) {
            self = .object(v)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Value is not a valid JSON primitive/array/object"
            )
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .string(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        }
    }
}

// MARK: - Date parsing

/// Parses the date-string shapes Airtable actually returns: full ISO 8601
/// with fractional seconds (`2024-01-15T10:30:00.000Z`), ISO 8601 without
/// (`2024-01-15T10:30:00Z`), and date-only fields (`2024-01-15`, decoded as
/// UTC midnight).
public enum AirtableDateParser {
    public static func parse(_ s: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: s) { return d }
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: s) { return d }
        let dateOnly = DateFormatter()
        dateOnly.dateFormat = "yyyy-MM-dd"
        dateOnly.timeZone = TimeZone(identifier: "UTC")
        dateOnly.locale = Locale(identifier: "en_US_POSIX")
        return dateOnly.date(from: s)
    }
}

extension JSONDecoder.DateDecodingStrategy {
    /// Decoding strategy for every wire payload: accepts the ISO 8601 and
    /// date-only string shapes Airtable returns (see `AirtableDateParser`).
    public static var airtable: JSONDecoder.DateDecodingStrategy {
        .custom { decoder in
            let container = try decoder.singleValueContainer()
            let s = try container.decode(String.self)
            guard let d = AirtableDateParser.parse(s) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Expected ISO 8601 or YYYY-MM-DD date string, got '\(s)'."
                )
            }
            return d
        }
    }
}
