import Foundation

// MARK: - Combinators

/// Top-level formula combinators matching Airtable's logical functions.
public enum Formulas {
    /// Combine formulas with AND logic. Empty strings are filtered out.
    public static func and(_ args: String...) -> String { and(args) }
    public static func and(_ args: [String]) -> String {
        let filtered = args.filter { !$0.isEmpty }
        switch filtered.count {
        case 0: return ""
        case 1: return filtered[0]
        default: return "AND(\(filtered.joined(separator: ",")))"
        }
    }

    /// Combine formulas with OR logic. Empty strings are filtered out.
    public static func or(_ args: String...) -> String { or(args) }
    public static func or(_ args: [String]) -> String {
        let filtered = args.filter { !$0.isEmpty }
        switch filtered.count {
        case 0: return ""
        case 1: return filtered[0]
        default: return "OR(\(filtered.joined(separator: ",")))"
        }
    }

    /// Negate a formula.
    public static func not(_ formula: String) -> String {
        "NOT(\(formula))"
    }

    /// Exclusive OR. Empty strings are filtered out.
    public static func xor(_ args: String...) -> String { xor(args) }
    public static func xor(_ args: [String]) -> String {
        let filtered = args.filter { !$0.isEmpty }
        switch filtered.count {
        case 0: return ""
        case 1: return filtered[0]
        default: return "XOR(\(filtered.joined(separator: ",")))"
        }
    }
}

// MARK: - Helpers

private func wrapField(_ field: String, caseSensitive: Bool, trim: Bool) -> String {
    var v = field
    if trim { v = "TRIM(\(v))" }
    if !caseSensitive { v = "LOWER(\(v))" }
    return v
}

/// Escape a value for an Airtable double-quoted formula string. Backslashes
/// are escaped FIRST, then quotes — otherwise a trailing `\` leaves the
/// closing quote live and the remainder of the value executes as formula
/// code (myairtable-53ip).
func escapeFormulaString(_ value: String) -> String {
    value
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
}

/// Escape a value for an Airtable single-quoted formula string.
func escapeFormulaStringSingle(_ value: String) -> String {
    value
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "'", with: "\\'")
}

private func wrapValueStr(_ value: String, caseSensitive: Bool, trim: Bool) -> String {
    var v = "\"\(escapeFormulaString(value))\""
    if trim { v = "TRIM(\(v))" }
    if !caseSensitive { v = "LOWER(\(v))" }
    return v
}

// MARK: - FormulaField protocol

/// Base protocol for all formula field types. Provides field reference and
/// empty/not-empty checks.
public protocol FormulaField {
    var fieldId: String { get }
}

extension FormulaField {
    /// Airtable field reference: `{fieldId}`.
    public var field: String { "{\(fieldId)}" }

    /// Field is blank.
    public func empty() -> String { "\(field)=BLANK()" }

    /// Field is not blank.
    public func notEmpty() -> String { "\(field)!=BLANK()" }
}

// MARK: - Text operations

/// Text operations shared by text, select, and lookup fields.
public protocol FormulaTextOps: FormulaField {
    /// Field reference used in string operations (FIND/LEN with LOWER/TRIM).
    /// Lookup fields override this to wrap the reference in
    /// `ARRAYJOIN(field, ", ")` so Airtable can coerce the array to a string.
    var stringField: String { get }
}

extension FormulaTextOps {
    /// Defaults to the bare `{field}` reference.
    public var stringField: String { field }

    /// Exact equality.
    public func equals(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(field, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "\(f)=\(v)"
    }

    /// Equals any of the given values.
    public func equalsAny(_ values: [String], caseSensitive: Bool = true, trim: Bool = false) -> String {
        Formulas.or(values.map { equals($0, caseSensitive: caseSensitive, trim: trim) })
    }

    /// Not equal.
    public func notEquals(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(field, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "\(f)!=\(v)"
    }

    /// Contains substring.
    public func contains(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(stringField, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "FIND(\(v),\(f))>0"
    }

    /// Contains any of the given values.
    public func containsAny(_ values: [String], caseSensitive: Bool = true, trim: Bool = false) -> String {
        Formulas.or(values.map { contains($0, caseSensitive: caseSensitive, trim: trim) })
    }

    /// Contains all of the given values.
    public func containsAll(_ values: [String], caseSensitive: Bool = true, trim: Bool = false) -> String {
        Formulas.and(values.map { contains($0, caseSensitive: caseSensitive, trim: trim) })
    }

    /// Does not contain substring.
    public func notContains(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        Formulas.not(contains(value, caseSensitive: caseSensitive, trim: trim))
    }

    /// Starts with the given value.
    public func startsWith(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(stringField, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "FIND(\(v),\(f))=1"
    }

    /// Does not start with the given value.
    public func notStartsWith(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(stringField, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "FIND(\(v),\(f))!=1"
    }

    /// Ends with the given value.
    public func endsWith(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(stringField, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "FIND(\(v),\(f))=LEN(\(f))-LEN(\(v))+1"
    }

    /// Does not end with the given value.
    public func notEndsWith(_ value: String, caseSensitive: Bool = true, trim: Bool = false) -> String {
        let f = wrapField(stringField, caseSensitive: caseSensitive, trim: trim)
        let v = wrapValueStr(value, caseSensitive: caseSensitive, trim: trim)
        return "FIND(\(v),\(f))!=LEN(\(f))-LEN(\(v))+1"
    }

    /// Phone number equality (strips spaces, dashes, parens, plus, dots).
    public func phoneEquals(_ value: String) -> String {
        let normalized = value.filter { !" -().+".contains($0) }
        let strip = { (s: String) -> String in
            "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(\(s),\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")"
        }
        return "\(strip(field))=\"\(escapeFormulaString(normalized))\""
    }

    /// Regex match.
    public func regexMatch(_ pattern: String) -> String {
        // Escape for the formula-string context only; regex escapes like \\d
        // become \\\\d in the formula source, which Airtable's parser unescapes
        // back before handing the pattern to the regex engine.
        return "REGEX_MATCH(\(field),\"\(escapeFormulaString(pattern))\")"
    }
}

// MARK: - Record ID

/// Formula builder for record IDs.
public struct FormulaId: Sendable {
    public init() {}

    /// Match a specific record ID.
    public func equals(_ id: String) -> String {
        "RECORD_ID()='\(escapeFormulaStringSingle(id))'"
    }

    /// Match any of the given record IDs.
    public func inList(_ ids: [String]) -> String {
        switch ids.count {
        case 0: return "FALSE()"
        case 1: return equals(ids[0])
        default: return Formulas.or(ids.map { equals($0) })
        }
    }
}

// MARK: - Text Field

/// Formula builder for text fields.
public struct FormulaTextField: FormulaField, FormulaTextOps, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }
}

// MARK: - Lookup Field

/// Formula builder for `multipleLookupValues` / lookup fields.
///
/// Lookup field values are arrays. Airtable does not auto-coerce arrays through
/// `LOWER` / `TRIM` / `FIND`, so `contains`, `startsWith` and `endsWith` would
/// silently match nothing. `stringField` wraps the reference in
/// `ARRAYJOIN(field, ", ")` so string ops see a string.
///
/// Equality (`=`) is unaffected — Airtable coerces array fields to a
/// comma-joined string under `=`, so direct equality already works.
public struct FormulaLookupField: FormulaField, FormulaTextOps, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }

    public var stringField: String { "ARRAYJOIN(\(field), \", \")" }
}

// MARK: - Single Select Field

/// Formula builder for single-select fields.
public struct FormulaSingleSelectField: FormulaField, FormulaTextOps, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }
}

// MARK: - Multi Select Field

/// Formula builder for multi-select fields.
public struct FormulaMultiSelectField: FormulaField, FormulaTextOps, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }
}

// MARK: - Number Field

/// Formula builder for number fields.
public struct FormulaNumberField: FormulaField, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }

    /// Equal to value.
    public func equals<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)=\(value)"
    }

    /// Not equal to value.
    public func notEquals<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)!=\(value)"
    }

    /// Greater than value.
    public func greaterThan<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)>\(value)"
    }

    /// Less than value.
    public func lessThan<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)<\(value)"
    }

    /// Greater than or equal to value.
    public func greaterThanOrEquals<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)>=\(value)"
    }

    /// Less than or equal to value.
    public func lessThanOrEquals<N: CustomStringConvertible>(_ value: N) -> String {
        "\(field)<=\(value)"
    }

    /// Between min and max. Inclusive by default.
    public func between<N: CustomStringConvertible>(_ min: N, _ max: N, inclusive: Bool = true) -> String {
        if inclusive {
            return Formulas.and(greaterThanOrEquals(min), lessThanOrEquals(max))
        } else {
            return Formulas.and(greaterThan(min), lessThan(max))
        }
    }
}

// MARK: - Boolean Field

/// Formula builder for checkbox/boolean fields.
public struct FormulaBooleanField: FormulaField, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }

    /// Equal to boolean value.
    public func equals(_ value: Bool) -> String {
        value ? isTrue() : isFalse()
    }

    /// Field is checked/true.
    public func isTrue() -> String { "\(field)=TRUE()" }

    /// Field is unchecked/false.
    public func isFalse() -> String { "\(field)=FALSE()" }
}

// MARK: - Date Field

/// Intermediate builder for date "time ago" comparisons.
/// Either side of a date comparison: a literal date string or another date field.
public protocol FormulaDateOperand {
    /// The operand wrapped in `DATETIME_PARSE(...)` for comparison.
    var datetimeParseExpr: String { get }
}

extension String: FormulaDateOperand {
    public var datetimeParseExpr: String { "DATETIME_PARSE('\(escapeFormulaStringSingle(self))')" }
}

public struct FormulaDateComparison: Sendable {
    let fieldId: String
    let op: String

    /// Compare against a literal date string or another date field.
    public func date(_ other: some FormulaDateOperand) -> String {
        "\(other.datetimeParseExpr)\(op)DATETIME_PARSE({\(fieldId)})"
    }

    public func millisecondsAgo(_ n: Int) -> String { ago(n, "milliseconds") }
    public func secondsAgo(_ n: Int) -> String { ago(n, "seconds") }
    public func minutesAgo(_ n: Int) -> String { ago(n, "minutes") }
    public func hoursAgo(_ n: Int) -> String { ago(n, "hours") }
    public func daysAgo(_ n: Int) -> String { ago(n, "days") }
    public func weeksAgo(_ n: Int) -> String { ago(n, "weeks") }
    public func monthsAgo(_ n: Int) -> String { ago(n, "months") }
    public func quartersAgo(_ n: Int) -> String { ago(n, "quarters") }
    public func yearsAgo(_ n: Int) -> String { ago(n, "years") }

    private func ago(_ n: Int, _ unit: String) -> String {
        "DATETIME_DIFF(NOW(),{\(fieldId)},\"\(unit)\")\(op)\(n)"
    }
}

/// Formula builder for date fields.
public struct FormulaDateField: FormulaField, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }

    private func comparison(_ op: String) -> FormulaDateComparison {
        FormulaDateComparison(fieldId: fieldId, op: op)
    }

    /// Date equals. Pass a date string or another date field.
    public func on(_ date: some FormulaDateOperand) -> String { comparison("=").date(date) }
    /// Returns a DateComparison for chaining with time-ago methods.
    public func on() -> FormulaDateComparison { comparison("=") }

    public func notOn(_ date: some FormulaDateOperand) -> String { comparison("!=").date(date) }
    public func notOn() -> FormulaDateComparison { comparison("!=") }

    public func onOrAfter(_ date: some FormulaDateOperand) -> String { comparison("<=").date(date) }
    public func onOrAfter() -> FormulaDateComparison { comparison("<=") }

    public func onOrBefore(_ date: some FormulaDateOperand) -> String { comparison(">=").date(date) }
    public func onOrBefore() -> FormulaDateComparison { comparison(">=") }

    public func after(_ date: some FormulaDateOperand) -> String { comparison("<").date(date) }
    public func after() -> FormulaDateComparison { comparison("<") }

    public func before(_ date: some FormulaDateOperand) -> String { comparison(">").date(date) }
    public func before() -> FormulaDateComparison { comparison(">") }

    /// Date is between start and end. Inclusive by default.
    public func between(
        _ start: some FormulaDateOperand, _ end: some FormulaDateOperand, inclusive: Bool = true
    ) -> String {
        if inclusive {
            return Formulas.and(onOrAfter(start), onOrBefore(end))
        } else {
            return Formulas.and(after(start), before(end))
        }
    }
}

extension FormulaDateField: FormulaDateOperand {
    public var datetimeParseExpr: String { "DATETIME_PARSE(\(field))" }
}

// MARK: - Attachments Field

/// Formula builder for attachment fields.
public struct FormulaAttachmentsField: FormulaField, Sendable {
    public let fieldId: String
    public init(_ fieldId: String) { self.fieldId = fieldId }

    /// Has exactly N attachments.
    public func count(_ n: Int) -> String { "LEN(\(field))=\(n)" }

    /// Has no attachments.
    public func empty() -> String { "LEN(\(field))=0" }

    /// Has attachments.
    public func notEmpty() -> String { "LEN(\(field))>0" }
}
