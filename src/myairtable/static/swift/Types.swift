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
    case multiple([T?])

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        // List items are nullable: Airtable rollup/lookup arrays can contain
        // `null` entries when the source field is missing on a linked record.
        if let arr = try? container.decode([T?].self) {
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

    /// The single value, or `nil` if this is the list shape.
    public var single: T? {
        if case .single(let v) = self { return v }
        return nil
    }

    /// The list of values, or `nil` if this is the single shape.
    public var multiple: [T?]? {
        if case .multiple(let arr) = self { return arr }
        return nil
    }

    /// Flatten to non-nil values regardless of encoding.
    public var values: [T] {
        switch self {
        case .single(let v): return [v]
        case .multiple(let v): return v.compactMap { $0 }
        }
    }
}

extension VecOrValue: Equatable where T: Equatable {}

/// A type-erased JSON value used where Airtable's schema doesn't constrain a
/// field's shape (e.g., `UNKNOWN` fields, raw `DictTable` values). Codable and
/// Sendable so it can flow through strict-concurrency code paths.
/// Reduce attachment cells to the only shape Airtable accepts when inserting.
///
/// Airtable returns attachments carrying read-only metadata (`id`, `size`, `type`, `width`,
/// `height`, `thumbnails`). On **create** it accepts only `{"url": ...}` (optionally with
/// `"filename"`) — sending an `id`, alone or echoed alongside `url`, fails with
/// `INVALID_ATTACHMENT_OBJECT`. Airtable re-ingests the file and mints a fresh attachment id,
/// which is what makes a duplicated record's attachment independent of its source rather than
/// an alias.
///
/// Create-only: on **update** an `id` is legal and means "retain this attachment".
///
/// Cells are recognised by shape rather than by field id, so this needs no generated metadata:
/// no other Airtable cell type is an array of objects carrying a `url` alongside an
/// `att`-prefixed id.
public func projectAttachmentsForCreate(
    _ fields: [String: AirtableJSONValue]
) -> [String: AirtableJSONValue] {
    var projectedFields = fields
    for (key, value) in fields {
        guard case .array(let items) = value, !items.isEmpty else { continue }

        var projected: [AirtableJSONValue] = []
        projected.reserveCapacity(items.count)
        var isAttachmentCell = true
        for item in items {
            guard case .object(let object) = item,
                let url = object["url"],
                case .string(let id) = object["id"] ?? .null,
                id.hasPrefix("att")
            else {
                isAttachmentCell = false
                break
            }
            var entry: [String: AirtableJSONValue] = ["url": url]
            if let filename = object["filename"], filename != .null {
                entry["filename"] = filename
            }
            projected.append(.object(entry))
        }
        if isAttachmentCell {
            projectedFields[key] = .array(projected)
        }
    }
    return projectedFields
}

/// Reduce a *typed* attachment cell to the only shape Airtable accepts when inserting.
///
/// The model-level counterpart to `projectAttachmentsForCreate`, and it exists because
/// `OrmTable.create(_:)` sends `model.toRecord()` verbatim — only `duplicate(_:)` projects.
/// So a model that is going to be inserted has to arrive already projected, which is what
/// the generated `copy()` does.
///
/// Where the JSON-level projector has to sniff shapes (an array of objects carrying a `url`
/// beside an `att`-prefixed `id`), this one needs no sniffing at all: the generator knows at
/// emit time which cells are attachment-typed *and* writable, and emits a call for exactly
/// those. That static split is also what keeps a computed attachment-shaped cell out of here
/// — a lookup of an attachment field decodes to the identical struct, but it is never written
/// back, so stripping its `id`/`size`/`type`/`thumbnails` would lose fidelity for nothing.
///
/// `nil` in, `nil` out. An absent cell means "field not set"; an *empty* attachment list means
/// "clear this cell", and conflating the two would silently wipe the copy's attachments.
public func projectAttachmentsForCopy(_ attachments: [AirtableAttachment]?) -> [AirtableAttachment]? {
    guard let attachments else { return nil }
    return attachments.map(projectAttachmentForCopy)
}

/// Scalar overload of `projectAttachmentsForCopy(_:)`. `GenericType.ATTACHMENT` renders as a
/// bare `AirtableAttachment`, so the generator's type-driven emission rule can produce this
/// call shape; today `multipleAttachments` is the only writable attachment field type and it
/// always renders as a list.
public func projectAttachmentsForCopy(_ attachment: AirtableAttachment?) -> AirtableAttachment? {
    guard let attachment else { return nil }
    return projectAttachmentForCopy(attachment)
}

/// `VecOrValue` overload of `projectAttachmentsForCopy(_:)`. Unreachable from today's schema —
/// the union wrapper is only applied to lookup/rollup cells, which are computed and therefore
/// never projected — but it means the emission rule (any *writable* cell whose Swift type
/// mentions `AirtableAttachment`) cannot produce a call that fails to compile.
public func projectAttachmentsForCopy(_ cell: VecOrValue<AirtableAttachment>?) -> VecOrValue<AirtableAttachment>? {
    guard let cell else { return nil }
    switch cell {
    case .single(let value): return .single(projectAttachmentForCopy(value))
    case .multiple(let values): return .multiple(values.map { $0.map(projectAttachmentForCopy) })
    }
}

/// The one-attachment core of `projectAttachmentsForCopy(_:)`.
///
/// Rebuilds rather than mutates: `AirtableAttachment`'s fields are `let`, and dropping the
/// server metadata is the entire point — echoing an `id` back on create fails with
/// `INVALID_ATTACHMENT_OBJECT`, and Airtable re-ingesting the file from `url` is what makes the
/// copy's attachment its own file rather than an alias of the source's.
private func projectAttachmentForCopy(_ attachment: AirtableAttachment) -> AirtableAttachment {
    AirtableAttachment(url: attachment.url, filename: attachment.filename)
}

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

// MARK: - Computed-field error / special values

/// An Airtable special number value (NaN, Infinity, -Infinity).
///
/// Returned by formula fields when the computation produces a non-finite
/// number. JSON shape: `{"specialValue": "NaN"}`. Only the object form is
/// accepted — a bare string or lookup-style array must not decode as this.
public struct SpecialNumber: Codable, Sendable, Equatable {
    public let specialValue: String

    public init(_ specialValue: String) { self.specialValue = specialValue }
}

/// An Airtable error value from a failed formula computation.
///
/// JSON shape: `{"error": "#ERROR!"}`. Only the object form is accepted.
public struct ErrorValue: Codable, Sendable, Equatable {
    public let error: String

    public init(_ error: String) { self.error = error }
}

/// Wraps a computed field that may be a value, special number, or error.
///
/// Airtable returns `{"specialValue": ...}` / `{"error": ...}` objects for
/// formula / rollup / lookup fields whose computation is non-finite or fails.
/// Decode order matters: the expected value is tried first so plain values
/// are never misinterpreted as the object-shaped fallbacks.
public enum MaybeSpecialOrError<T: Codable & Sendable>: Codable, Sendable {
    case value(T)
    case special(SpecialNumber)
    case error(ErrorValue)

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(T.self) {
            self = .value(v)
        } else if let s = try? container.decode(SpecialNumber.self) {
            self = .special(s)
        } else if let e = try? container.decode(ErrorValue.self) {
            self = .error(e)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription:
                    "Expected \(T.self), {\"specialValue\": ...}, or {\"error\": ...}"
            )
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .value(let v): try container.encode(v)
        case .special(let s): try container.encode(s)
        case .error(let e): try container.encode(e)
        }
    }

    /// The wrapped value, or `nil` for special/error variants.
    public var value: T? {
        if case .value(let v) = self { return v }
        return nil
    }

    public var special: SpecialNumber? {
        if case .special(let s) = self { return s }
        return nil
    }

    public var errorValue: ErrorValue? {
        if case .error(let e) = self { return e }
        return nil
    }

    public var isValue: Bool { value != nil }
    public var isSpecial: Bool { special != nil }
    public var isError: Bool { errorValue != nil }
}

extension MaybeSpecialOrError: Equatable where T: Equatable {}
