import Foundation

/// Query parameters for Airtable list-records requests. Builder-style:
/// create, chain mutations, pass to a table's list method.
///
/// `Sendable` so instances can cross actor boundaries (e.g., from a model
/// main-actor call into the `AirtableClient` actor).
public struct AirtableQuery: Sendable, Equatable {
    public var formula: String?
    public var sort: [Sort]
    public var fields: [String]
    public var maxRecords: Int?
    public var pageSize: Int?
    public var view: String?
    public var returnFieldsByFieldId: Bool
    public var cellFormat: CellFormat
    public var timeZone: String?
    public var userLocale: String?

    public enum CellFormat: String, Sendable {
        case json
        case string
    }

    public init(
        formula: String? = nil,
        sort: [Sort] = [],
        fields: [String] = [],
        maxRecords: Int? = nil,
        pageSize: Int? = nil,
        view: String? = nil,
        returnFieldsByFieldId: Bool = true,
        cellFormat: CellFormat = .json,
        timeZone: String? = nil,
        userLocale: String? = nil
    ) {
        self.formula = formula
        self.sort = sort
        self.fields = fields
        self.maxRecords = maxRecords
        self.pageSize = pageSize
        self.view = view
        self.returnFieldsByFieldId = returnFieldsByFieldId
        self.cellFormat = cellFormat
        self.timeZone = timeZone
        self.userLocale = userLocale
    }

    // MARK: - Fluent builders

    public func withFormula(_ formula: String?) -> AirtableQuery {
        var copy = self
        copy.formula = formula
        return copy
    }

    public func withSort(_ sort: [Sort]) -> AirtableQuery {
        var copy = self
        copy.sort = sort
        return copy
    }

    public func withSort(field: String, direction: SortDirection = .asc) -> AirtableQuery {
        var copy = self
        copy.sort.append(Sort(field: field, direction: direction))
        return copy
    }

    public func withFields(_ fields: [String]) -> AirtableQuery {
        var copy = self
        copy.fields = fields
        return copy
    }

    public func withMaxRecords(_ maxRecords: Int?) -> AirtableQuery {
        var copy = self
        copy.maxRecords = maxRecords
        return copy
    }

    public func withPageSize(_ pageSize: Int?) -> AirtableQuery {
        var copy = self
        copy.pageSize = pageSize
        return copy
    }

    public func withView(_ view: String?) -> AirtableQuery {
        var copy = self
        copy.view = view
        return copy
    }

    // MARK: - URL encoding

    /// Convert to `[URLQueryItem]` using Airtable's list-records parameter shape:
    /// `filterByFormula`, `fields[]`, `sort[i][field]`, `sort[i][direction]`,
    /// `maxRecords`, `pageSize`, `view`, `returnFieldsByFieldId`, `cellFormat`,
    /// `timeZone`, `userLocale`.
    public func toQueryItems() -> [URLQueryItem] {
        var items: [URLQueryItem] = []

        if let formula = formula, !formula.isEmpty {
            items.append(URLQueryItem(name: "filterByFormula", value: formula))
        }

        for field in fields {
            items.append(URLQueryItem(name: "fields[]", value: field))
        }

        for (i, s) in sort.enumerated() {
            items.append(URLQueryItem(name: "sort[\(i)][field]", value: s.field))
            items.append(URLQueryItem(name: "sort[\(i)][direction]", value: s.direction.rawValue))
        }

        if let maxRecords = maxRecords {
            items.append(URLQueryItem(name: "maxRecords", value: String(maxRecords)))
        }

        if let pageSize = pageSize {
            items.append(URLQueryItem(name: "pageSize", value: String(pageSize)))
        }

        if let view = view, !view.isEmpty {
            items.append(URLQueryItem(name: "view", value: view))
        }

        if returnFieldsByFieldId {
            items.append(URLQueryItem(name: "returnFieldsByFieldId", value: "true"))
        }

        if cellFormat != .json {
            items.append(URLQueryItem(name: "cellFormat", value: cellFormat.rawValue))
        }

        if let tz = timeZone, !tz.isEmpty {
            items.append(URLQueryItem(name: "timeZone", value: tz))
        }

        if let locale = userLocale, !locale.isEmpty {
            items.append(URLQueryItem(name: "userLocale", value: locale))
        }

        return items
    }
}
