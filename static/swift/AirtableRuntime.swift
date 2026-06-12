// AirtableRuntime: implements Airtable formula functions and operators.
//
// All operators route through this enum for correct Airtable semantics:
// - BLANK() is nil (treated as 0 numerically, "" as string)
// - Type coercion follows Airtable rules (booleans → 1/0, strings parsed to numbers, etc.)
// - Division by zero returns .double(.nan) for consistency
//
// Values flow as `AirtableJSONValue` so functions compose naturally.
// Ported from static/rust/airtable_runtime.rs + static/python/airtable_runtime.py.

import Foundation

public enum AirtableRuntime {

    // =========================================================================
    // MARK: - Coercion helpers (F8.3)
    // =========================================================================

    /// Coerce to a `Double`. `nil`/`null` → 0. Booleans → 1/0. Strings parse or 0. Arrays → first element.
    public static func N(_ v: AirtableJSONValue?) -> Double {
        guard let v = v else { return 0 }
        switch v {
        case .null: return 0
        case .bool(let b): return b ? 1 : 0
        case .int(let i): return Double(i)
        case .double(let d): return d
        case .string(let s):
            return Double(s.trimmingCharacters(in: .whitespaces)) ?? 0
        case .array(let arr): return arr.isEmpty ? 0 : N(arr[0])
        case .object: return 0
        }
    }

    /// Coerce to `String`. Airtable strips `.0` from whole-number floats.
    public static func S(_ v: AirtableJSONValue?) -> String {
        guard let v = v else { return "" }
        switch v {
        case .null: return ""
        case .bool(let b): return b ? "1" : "0"
        case .int(let i): return String(i)
        case .double(let d):
            if d.isFinite && d == d.rounded() && abs(d) < 1e15 {
                return String(Int64(d))
            }
            return String(d)
        case .string(let s): return s
        case .array(let arr): return arr.isEmpty ? "" : S(arr[0])
        case .object: return ""
        }
    }

    /// Flatten args into a single `[AirtableJSONValue]`.
    public static func A(_ args: [AirtableJSONValue?]) -> [AirtableJSONValue] {
        var out: [AirtableJSONValue] = []
        for a in args {
            guard let a = a else { continue }
            if case .array(let inner) = a {
                out.append(contentsOf: inner)
            } else {
                out.append(a)
            }
        }
        return out
    }

    /// Flatten + coerce to numbers.
    public static func AN(_ args: [AirtableJSONValue?]) -> [Double] {
        A(args).map { N($0) }
    }

    /// Flatten + coerce to strings.
    public static func AS(_ args: [AirtableJSONValue?]) -> [String] {
        A(args).map { S($0) }
    }

    /// Convert any `Encodable` value to `AirtableJSONValue` for runtime composition.
    /// Used by the transpiler to wrap model field references (e.g. `V(self.numberInt)`).
    /// `nil` inputs produce `.null`. Failures fall through to `.null` rather than
    /// throwing — formulas prefer BLANK-like propagation over hard errors.
    public static func V<T: Encodable>(_ v: T?) -> AirtableJSONValue {
        guard let v = v else { return .null }
        let enc = JSONEncoder()
        enc.dateEncodingStrategy = .iso8601
        guard let data = try? enc.encode(v) else { return .null }
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .airtable
        return (try? dec.decode(AirtableJSONValue.self, from: data)) ?? .null
    }

    /// Pass-through for values already in `AirtableJSONValue` form.
    public static func V(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        v ?? .null
    }

    /// Coerce to `Date`. ISO 8601 strings, Unix timestamps, or `nil`.
    public static func D(_ v: AirtableJSONValue?) -> Date? {
        guard let v = v else { return nil }
        switch v {
        case .null: return nil
        case .int(let i): return Date(timeIntervalSince1970: TimeInterval(i))
        case .double(let d): return Date(timeIntervalSince1970: d)
        case .string(let s):
            return _parseIsoDate(s)
        case .array(let arr): return arr.isEmpty ? nil : D(arr[0])
        default: return nil
        }
    }

    private static func _parseIsoDate(_ s: String) -> Date? {
        AirtableDateParser.parse(s)
    }

    // =========================================================================
    // MARK: - Truthiness + special values (F8.4 logic)
    // =========================================================================

    public static func isTruthy(_ v: AirtableJSONValue?) -> Bool {
        guard let v = v else { return false }
        switch v {
        case .null: return false
        case .bool(let b): return b
        case .int(let i): return i != 0
        case .double(let d): return d != 0 && !d.isNaN
        case .string(let s): return !s.isEmpty
        case .array(let arr): return !arr.isEmpty
        case .object(let o): return !o.isEmpty
        }
    }

    public static func BLANK() -> AirtableJSONValue { .null }
    public static func TRUE() -> AirtableJSONValue { .bool(true) }
    public static func FALSE() -> AirtableJSONValue { .bool(false) }

    public static func IF(
        _ condition: AirtableJSONValue?,
        _ ifTrue: AirtableJSONValue?,
        _ ifFalse: AirtableJSONValue?
    ) -> AirtableJSONValue {
        isTruthy(condition) ? (ifTrue ?? .null) : (ifFalse ?? .null)
    }

    public static func SWITCH(
        _ expr: AirtableJSONValue?,
        cases: [(AirtableJSONValue, AirtableJSONValue)],
        default defaultValue: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let key = S(expr)
        for (candidate, value) in cases where S(candidate) == key {
            return value
        }
        return defaultValue ?? .null
    }

    /// ISERROR returns true for NaN doubles — signals a computation error.
    public static func ISERROR(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        if case .double(let d) = v, d.isNaN { return .bool(true) }
        return .bool(false)
    }

    public static func ERROR(_ message: AirtableJSONValue? = nil) -> AirtableJSONValue {
        // Surface as NaN so ISERROR picks it up.
        _ = message
        return .double(.nan)
    }

    // =========================================================================
    // MARK: - Math functions (F8.4)
    // =========================================================================

    private static func numValue(_ d: Double) -> AirtableJSONValue {
        if d.isFinite && d == d.rounded() && abs(d) < 1e15 {
            return .int(Int(d))
        }
        return .double(d)
    }

    public static func SUM(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        numValue(AN(args).reduce(0, +))
    }

    public static func AVERAGE(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        let nums = AN(args)
        guard !nums.isEmpty else { return .double(.nan) }
        return numValue(nums.reduce(0, +) / Double(nums.count))
    }

    public static func MIN(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        let nums = AN(args)
        guard let m = nums.min() else { return .double(.nan) }
        return numValue(m)
    }

    public static func MAX(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        let nums = AN(args)
        guard let m = nums.max() else { return .double(.nan) }
        return numValue(m)
    }

    public static func COUNT(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        let flat = A(args)
        let c = flat.reduce(into: 0) { acc, v in
            switch v {
            case .int, .double: acc += 1
            default: break
            }
        }
        return .int(c)
    }

    public static func COUNTA(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        let flat = A(args)
        let c = flat.reduce(into: 0) { acc, v in
            switch v {
            case .null: break
            case .string(let s) where s.isEmpty: break
            default: acc += 1
            }
        }
        return .int(c)
    }

    public static func ROUND(_ v: AirtableJSONValue?, _ precision: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        let p = Int(N(precision))
        let factor = pow(10.0, Double(p))
        return numValue((n * factor).rounded() / factor)
    }

    public static func ROUNDUP(_ v: AirtableJSONValue?, _ precision: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        let p = Int(N(precision))
        let factor = pow(10.0, Double(p))
        let r = n >= 0 ? ceil(n * factor) / factor : floor(n * factor) / factor
        return numValue(r)
    }

    public static func ROUNDDOWN(_ v: AirtableJSONValue?, _ precision: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        let p = Int(N(precision))
        let factor = pow(10.0, Double(p))
        let r = n >= 0 ? floor(n * factor) / factor : ceil(n * factor) / factor
        return numValue(r)
    }

    public static func CEILING(_ v: AirtableJSONValue?, _ significance: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        let s = significance.map { N($0) } ?? 1
        let sig = s == 0 ? 1 : s
        return numValue(ceil(n / sig) * sig)
    }

    public static func FLOOR(_ v: AirtableJSONValue?, _ significance: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        let s = significance.map { N($0) } ?? 1
        let sig = s == 0 ? 1 : s
        return numValue(floor(n / sig) * sig)
    }

    public static func LOG(_ v: AirtableJSONValue?, _ base: AirtableJSONValue? = nil) -> AirtableJSONValue {
        let n = N(v)
        if let base = base {
            return numValue(log(n) / log(N(base)))
        }
        return numValue(log10(n))
    }

    public static func EVEN(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        let n = N(v)
        let c = ceil(abs(n))
        var r = c.truncatingRemainder(dividingBy: 2) == 0 ? c : c + 1
        if n < 0 { r = -r }
        return .int(Int(r))
    }

    public static func ODD(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        let n = N(v)
        let c = ceil(abs(n))
        var r = c.truncatingRemainder(dividingBy: 2) == 1 ? c : c + 1
        if n < 0 { r = -r }
        return .int(Int(r))
    }

    public static func VALUE(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let v = v else { return .int(0) }
        let s = S(v)
        if s.contains(".") {
            if let d = Double(s) { return .double(d) }
        } else if let i = Int(s) {
            return .int(i)
        }
        return .double(.nan)
    }

    public static func POWER(_ base: AirtableJSONValue?, _ exp: AirtableJSONValue?) -> AirtableJSONValue {
        numValue(pow(N(base), N(exp)))
    }

    public static func MOD(_ v: AirtableJSONValue?, _ divisor: AirtableJSONValue?) -> AirtableJSONValue {
        let d = N(divisor)
        guard d != 0 else { return .double(.nan) }
        return numValue(N(v).truncatingRemainder(dividingBy: d))
    }

    public static func ABS(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        numValue(abs(N(v)))
    }

    public static func EXP(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        numValue(Darwin.exp(N(v)))
    }

    public static func SQRT(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        numValue(sqrt(N(v)))
    }

    public static func INT(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        let n = N(v)
        return .int(Int(n.rounded(.down)))
    }

    // =========================================================================
    // MARK: - String functions (F8.6)
    // =========================================================================

    public static func LEN(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        .int(S(v).count)
    }

    public static func LEFT(_ text: AirtableJSONValue?, _ count: AirtableJSONValue?) -> AirtableJSONValue {
        let s = S(text)
        let n = max(0, Int(N(count)))
        let idx = s.index(s.startIndex, offsetBy: min(n, s.count))
        return .string(String(s[..<idx]))
    }

    public static func RIGHT(_ text: AirtableJSONValue?, _ count: AirtableJSONValue?) -> AirtableJSONValue {
        let s = S(text)
        let n = max(0, Int(N(count)))
        let start = s.index(s.endIndex, offsetBy: -min(n, s.count))
        return .string(String(s[start...]))
    }

    public static func MID(
        _ text: AirtableJSONValue?,
        _ start: AirtableJSONValue?,
        _ count: AirtableJSONValue?
    ) -> AirtableJSONValue {
        let s = S(text)
        let startIdx = max(0, Int(N(start)) - 1)
        let len = max(0, Int(N(count)))
        guard startIdx < s.count else { return .string("") }
        let begin = s.index(s.startIndex, offsetBy: startIdx)
        let endOffset = min(startIdx + len, s.count)
        let end = s.index(s.startIndex, offsetBy: endOffset)
        return .string(String(s[begin..<end]))
    }

    public static func FIND(
        _ needle: AirtableJSONValue?,
        _ haystack: AirtableJSONValue?,
        _ start: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let hay = S(haystack)
        let nee = S(needle)
        let offset = start.map { max(0, Int(N($0)) - 1) } ?? 0
        guard offset < hay.count else { return .int(0) }
        let searchFrom = hay.index(hay.startIndex, offsetBy: offset)
        if let r = hay.range(of: nee, range: searchFrom..<hay.endIndex) {
            return .int(hay.distance(from: hay.startIndex, to: r.lowerBound) + 1)
        }
        return .int(0)
    }

    public static func SEARCH(
        _ needle: AirtableJSONValue?,
        _ haystack: AirtableJSONValue?,
        _ start: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let hay = S(haystack).lowercased()
        let nee = S(needle).lowercased()
        let offset = start.map { max(0, Int(N($0)) - 1) } ?? 0
        guard offset < hay.count else { return .int(0) }
        let searchFrom = hay.index(hay.startIndex, offsetBy: offset)
        if let r = hay.range(of: nee, range: searchFrom..<hay.endIndex) {
            return .int(hay.distance(from: hay.startIndex, to: r.lowerBound) + 1)
        }
        return .int(0)
    }

    public static func SUBSTITUTE(
        _ text: AirtableJSONValue?,
        _ old: AirtableJSONValue?,
        _ new: AirtableJSONValue?,
        _ occurrence: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let s = S(text)
        let o = S(old)
        let n = S(new)
        guard !o.isEmpty else { return .string(s) }
        guard let target = occurrence.map({ Int(N($0)) }) else {
            return .string(s.replacingOccurrences(of: o, with: n))
        }
        // Replace only the Nth occurrence.
        var result = s
        var current = 1
        var searchFrom = result.startIndex
        while let r = result.range(of: o, range: searchFrom..<result.endIndex) {
            if current == target {
                result.replaceSubrange(r, with: n)
                return .string(result)
            }
            current += 1
            searchFrom = result.index(r.lowerBound, offsetBy: 1, limitedBy: result.endIndex) ?? result.endIndex
        }
        return .string(result)
    }

    public static func REPLACE(
        _ text: AirtableJSONValue?,
        _ start: AirtableJSONValue?,
        _ count: AirtableJSONValue?,
        _ replacement: AirtableJSONValue?
    ) -> AirtableJSONValue {
        let s = S(text)
        let startIdx = max(0, Int(N(start)) - 1)
        let len = max(0, Int(N(count)))
        let r = S(replacement)
        guard startIdx <= s.count else { return .string(s + r) }
        let begin = s.index(s.startIndex, offsetBy: startIdx)
        let endOffset = min(startIdx + len, s.count)
        let end = s.index(s.startIndex, offsetBy: endOffset)
        return .string(String(s[..<begin]) + r + String(s[end...]))
    }

    public static func LOWER(_ v: AirtableJSONValue?) -> AirtableJSONValue { .string(S(v).lowercased()) }
    public static func UPPER(_ v: AirtableJSONValue?) -> AirtableJSONValue { .string(S(v).uppercased()) }
    public static func TRIM(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        .string(S(v).trimmingCharacters(in: .whitespaces))
    }

    public static func REPT(_ text: AirtableJSONValue?, _ count: AirtableJSONValue?) -> AirtableJSONValue {
        let s = S(text)
        let n = max(0, Int(N(count)))
        return .string(String(repeating: s, count: n))
    }

    public static func CONCATENATE(_ args: AirtableJSONValue?...) -> AirtableJSONValue {
        .string(args.map { S($0) }.joined())
    }

    public static func ENCODE_URL_COMPONENT(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        let s = S(v)
        return .string(s.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? s)
    }

    public static func T(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        if case .string(let s) = v { return .string(s) }
        return .string("")
    }

    // =========================================================================
    // MARK: - Date/time functions (F8.7)
    // =========================================================================

    private static func _iso(_ d: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: d)
    }

    public static func NOW() -> AirtableJSONValue { .string(_iso(Date())) }
    public static func TODAY() -> AirtableJSONValue {
        let cal = Calendar(identifier: .gregorian)
        let d = cal.startOfDay(for: Date())
        return .string(_iso(d))
    }

    public static func YEAR(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.year, from: d))
    }

    public static func MONTH(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.month, from: d))
    }

    public static func DAY(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.day, from: d))
    }

    public static func HOUR(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.hour, from: d))
    }

    public static func MINUTE(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.minute, from: d))
    }

    public static func SECOND(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return .int(cal.component(.second, from: d))
    }

    public static func WEEKDAY(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        // Airtable: Sunday=0, Monday=1, ..., Saturday=6.
        // Calendar.weekday returns 1 (Sunday) ... 7 (Saturday).
        return .int(cal.component(.weekday, from: d) - 1)
    }

    public static func DATETIME_DIFF(
        _ d1v: AirtableJSONValue?,
        _ d2v: AirtableJSONValue?,
        _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        guard let d1 = D(d1v), let d2 = D(d2v) else { return .int(0) }
        let diffSecs = d1.timeIntervalSince(d2)
        let u = S(unit).lowercased()
        let v: Double
        switch u {
        case "milliseconds": v = diffSecs * 1000
        case "seconds": v = diffSecs
        case "minutes": v = diffSecs / 60
        case "hours": v = diffSecs / 3600
        case "days", "": v = diffSecs / 86400
        case "weeks": v = diffSecs / (86400 * 7)
        case "months":
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = TimeZone(identifier: "UTC")!
            let y1 = cal.component(.year, from: d1)
            let m1 = cal.component(.month, from: d1)
            let y2 = cal.component(.year, from: d2)
            let m2 = cal.component(.month, from: d2)
            return .int((y1 - y2) * 12 + (m1 - m2))
        case "years":
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = TimeZone(identifier: "UTC")!
            return .int(cal.component(.year, from: d1) - cal.component(.year, from: d2))
        default: v = diffSecs / 86400
        }
        return .int(Int(v))
    }

    public static func DATEADD(
        _ date: AirtableJSONValue?,
        _ count: AirtableJSONValue?,
        _ unit: AirtableJSONValue?
    ) -> AirtableJSONValue {
        guard let d = D(date) else { return .null }
        let n = Int(N(count))
        let u = S(unit).lowercased()
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let comp: Calendar.Component
        switch u {
        case "years": comp = .year
        case "months": comp = .month
        case "weeks": comp = .weekOfYear
        case "days": comp = .day
        case "hours": comp = .hour
        case "minutes": comp = .minute
        case "seconds": comp = .second
        default: comp = .day
        }
        guard let result = cal.date(byAdding: comp, value: n, to: d) else { return .null }
        return .string(_iso(result))
    }

    public static func IS_SAME(
        _ d1: AirtableJSONValue?, _ d2: AirtableJSONValue?, _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let u = unit ?? .string("days")
        guard case .int(let v) = DATETIME_DIFF(d1, d2, u) else { return .bool(false) }
        return .bool(v == 0)
    }

    public static func IS_BEFORE(
        _ d1: AirtableJSONValue?, _ d2: AirtableJSONValue?, _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let u = unit ?? .string("days")
        guard case .int(let v) = DATETIME_DIFF(d1, d2, u) else { return .bool(false) }
        return .bool(v < 0)
    }

    public static func IS_AFTER(
        _ d1: AirtableJSONValue?, _ d2: AirtableJSONValue?, _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let u = unit ?? .string("days")
        guard case .int(let v) = DATETIME_DIFF(d1, d2, u) else { return .bool(false) }
        return .bool(v > 0)
    }

    /// Human-friendly duration string between two dates.
    private static func _humanDuration(_ d1v: AirtableJSONValue?, _ d2v: AirtableJSONValue?) -> String {
        guard let d1 = D(d1v), let d2 = D(d2v) else { return "" }
        let diff = abs(Int(d1.timeIntervalSince(d2)))
        let minutes = diff / 60
        let hours = minutes / 60
        let days = hours / 24
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let months = abs(
            (cal.component(.year, from: d1) - cal.component(.year, from: d2)) * 12
                + (cal.component(.month, from: d1) - cal.component(.month, from: d2))
        )
        let years = months / 12
        if years > 0 { return "\(years) year\(years == 1 ? "" : "s")" }
        if months > 0 { return "\(months) month\(months == 1 ? "" : "s")" }
        if days > 0 { return "\(days) day\(days == 1 ? "" : "s")" }
        if hours > 0 { return "\(hours) hour\(hours == 1 ? "" : "s")" }
        if minutes > 0 { return "\(minutes) minute\(minutes == 1 ? "" : "s")" }
        return "\(diff) second\(diff == 1 ? "" : "s")"
    }

    public static func TONOW(
        _ date: AirtableJSONValue?, _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        if unit != nil {
            return DATETIME_DIFF(NOW(), date, unit)
        }
        return .string(_humanDuration(date, NOW()))
    }

    public static func FROMNOW(
        _ date: AirtableJSONValue?, _ unit: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        if unit != nil {
            return DATETIME_DIFF(date, NOW(), unit)
        }
        return .string(_humanDuration(date, NOW()))
    }

    /// ISO 8601 week number (week starts on the supplied day; default Sunday).
    public static func WEEKNUM(
        _ date: AirtableJSONValue?, _ startDay: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        guard let d = D(date) else { return .int(0) }
        let names: [String: Int] = [
            "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4,
            "thursday": 5, "friday": 6, "saturday": 7,
        ]
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        cal.firstWeekday = names[S(startDay).lowercased()] ?? 1
        return .int(cal.component(.weekOfYear, from: d))
    }

    /// WORKDAY advances a date by N working days (Mon–Fri).
    public static func WORKDAY(
        _ start: AirtableJSONValue?, _ numDays: AirtableJSONValue?
    ) -> AirtableJSONValue {
        guard var d = D(start) else { return .null }
        var remaining = Int(N(numDays))
        let direction = remaining >= 0 ? 1 : -1
        remaining = abs(remaining)
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        while remaining > 0 {
            guard let next = cal.date(byAdding: .day, value: direction, to: d) else {
                return .null
            }
            d = next
            let wd = cal.component(.weekday, from: d)
            // Sunday=1, Saturday=7 → skip.
            if wd != 1 && wd != 7 { remaining -= 1 }
        }
        return .string(_iso(d))
    }

    /// Count working days (Mon–Fri) between two dates. Signed (start later → negative).
    public static func WORKDAY_DIFF(
        _ start: AirtableJSONValue?, _ end: AirtableJSONValue?
    ) -> AirtableJSONValue {
        guard let d1 = D(start), let d2 = D(end) else { return .int(0) }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        var count = 0
        var current = d1
        let direction = d2 > d1 ? 1 : -1
        if ![1, 7].contains(cal.component(.weekday, from: current)) { count += direction }
        while (direction == 1 && current < d2) || (direction == -1 && current > d2) {
            guard let next = cal.date(byAdding: .day, value: direction, to: current) else { break }
            current = next
            if ![1, 7].contains(cal.component(.weekday, from: current)) { count += direction }
        }
        return .int(count)
    }

    /// Reinterpret a datetime in a different timezone. Returns the wall-clock
    /// value as an ISO string (matching the Python runtime's behavior).
    public static func SET_TIMEZONE(
        _ date: AirtableJSONValue?, _ tz: AirtableJSONValue?
    ) -> AirtableJSONValue {
        guard let d = D(date) else { return .null }
        let name = S(tz)
        guard let zone = TimeZone(identifier: name) else { return .string(_iso(d)) }
        // Offset the UTC instant so the "clock face" matches the target zone.
        let offset = TimeInterval(zone.secondsFromGMT(for: d))
        let shifted = d.addingTimeInterval(offset)
        return .string(_iso(shifted))
    }

    public static func DATETIME_FORMAT(
        _ date: AirtableJSONValue?, _ fmt: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        guard let d = D(date) else { return .string("") }
        guard let fmt = fmt else { return .string(_iso(d)) }
        let f = S(fmt)
        let df = DateFormatter()
        df.timeZone = TimeZone(identifier: "UTC")
        // Moment.js → DateFormatter token mapping.
        df.dateFormat =
            f
            .replacingOccurrences(of: "YYYY", with: "yyyy")
            .replacingOccurrences(of: "YY", with: "yy")
            .replacingOccurrences(of: "DD", with: "dd")
        return .string(df.string(from: d))
    }

    public static func DATESTR(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .string("") }
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"
        df.timeZone = TimeZone(identifier: "UTC")
        return .string(df.string(from: d))
    }

    public static func TIMESTR(_ v: AirtableJSONValue?) -> AirtableJSONValue {
        guard let d = D(v) else { return .string("") }
        let df = DateFormatter()
        df.dateFormat = "HH:mm:ss"
        df.timeZone = TimeZone(identifier: "UTC")
        return .string(df.string(from: d))
    }

    public static func DATETIME_PARSE(
        _ s: AirtableJSONValue?, _ fmt: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        _ = fmt  // Input-format override is ignored — we try ISO 8601 then a few fallbacks.
        guard let d = D(s) else { return .null }
        return .string(_iso(d))
    }

    // =========================================================================
    // MARK: - Array functions (F8.8)
    // =========================================================================

    public static func ARRAYJOIN(
        _ arr: AirtableJSONValue?, _ separator: AirtableJSONValue? = nil
    ) -> AirtableJSONValue {
        let sep = separator.map { S($0) } ?? ", "
        guard let arr = arr else { return .string("") }
        if case .array(let items) = arr {
            return .string(items.map { S($0) }.joined(separator: sep))
        }
        return .string(S(arr))
    }

    public static func ARRAYUNIQUE(_ arr: AirtableJSONValue?) -> AirtableJSONValue {
        guard let arr = arr else { return .array([]) }
        guard case .array(let items) = arr else { return .array([arr]) }
        var seen: [AirtableJSONValue] = []
        for v in items where !seen.contains(v) { seen.append(v) }
        return .array(seen)
    }

    public static func ARRAYCOMPACT(_ arr: AirtableJSONValue?) -> AirtableJSONValue {
        guard let arr = arr else { return .array([]) }
        guard case .array(let items) = arr else { return .array([arr]) }
        return .array(
            items.filter {
                if case .null = $0 { return false }
                if case .string(let s) = $0, s.isEmpty { return false }
                return true
            })
    }

    public static func ARRAYFLATTEN(_ arr: AirtableJSONValue?) -> AirtableJSONValue {
        guard let arr = arr else { return .array([]) }
        guard case .array(let items) = arr else { return .array([arr]) }
        var out: [AirtableJSONValue] = []
        func flatten(_ xs: [AirtableJSONValue]) {
            for x in xs {
                if case .array(let inner) = x { flatten(inner) } else { out.append(x) }
            }
        }
        flatten(items)
        return .array(out)
    }

    // =========================================================================
    // MARK: - Regex (F8.9)
    // =========================================================================

    public static func REGEX_EXTRACT(
        _ text: AirtableJSONValue?, _ pattern: AirtableJSONValue?
    ) -> AirtableJSONValue {
        let s = S(text)
        let p = S(pattern)
        guard let re = try? NSRegularExpression(pattern: p),
            let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)),
            let range = Range(m.range, in: s)
        else { return .string("") }
        return .string(String(s[range]))
    }

    public static func REGEX_MATCH(
        _ text: AirtableJSONValue?, _ pattern: AirtableJSONValue?
    ) -> AirtableJSONValue {
        let s = S(text)
        let p = S(pattern)
        guard let re = try? NSRegularExpression(pattern: p) else { return .bool(false) }
        let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s))
        return .bool(m != nil)
    }

    public static func REGEX_REPLACE(
        _ text: AirtableJSONValue?, _ pattern: AirtableJSONValue?, _ replacement: AirtableJSONValue?
    ) -> AirtableJSONValue {
        let s = S(text)
        let p = S(pattern)
        let r = S(replacement)
        guard let re = try? NSRegularExpression(pattern: p) else { return .string(s) }
        let out = re.stringByReplacingMatches(
            in: s, range: NSRange(s.startIndex..., in: s), withTemplate: r
        )
        return .string(out)
    }
}
