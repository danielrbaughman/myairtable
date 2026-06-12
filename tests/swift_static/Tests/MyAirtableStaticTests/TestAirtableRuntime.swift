// F8.12 — Unit tests for AirtableRuntime. Mirrors a meaningful subset of
// tests/test_airtable_runtime.rs (~180 cases); we cover the core semantics
// here and lean on integration tests for end-to-end formula correctness.

import Foundation
import Testing

@testable import MyAirtableStatic

typealias V = AirtableJSONValue
typealias R = AirtableRuntime

// MARK: - Coercion (F8.3)

@Suite("Runtime coercion")
struct TestRuntimeCoercion {
    @Test func nNilIsZero() { #expect(R.N(nil) == 0) }
    @Test func nNullIsZero() { #expect(R.N(.null) == 0) }
    @Test func nBoolTrueIsOne() { #expect(R.N(.bool(true)) == 1) }
    @Test func nBoolFalseIsZero() { #expect(R.N(.bool(false)) == 0) }
    @Test func nIntPassesThrough() { #expect(R.N(.int(42)) == 42) }
    @Test func nDoublePassesThrough() { #expect(R.N(.double(3.14)) == 3.14) }
    @Test func nStringParses() { #expect(R.N(.string("5.5")) == 5.5) }
    @Test func nStringNonNumericIsZero() { #expect(R.N(.string("abc")) == 0) }
    @Test func nArrayReturnsFirst() { #expect(R.N(.array([.int(7), .int(8)])) == 7) }
    @Test func nEmptyArrayIsZero() { #expect(R.N(.array([])) == 0) }

    @Test func sNilIsEmpty() { #expect(R.S(nil) == "") }
    @Test func sNullIsEmpty() { #expect(R.S(.null) == "") }
    @Test func sBoolTrueIsOne() { #expect(R.S(.bool(true)) == "1") }
    @Test func sBoolFalseIsZero() { #expect(R.S(.bool(false)) == "0") }
    @Test func sIntIsDigits() { #expect(R.S(.int(42)) == "42") }
    @Test func sDoubleWholeStrips() { #expect(R.S(.double(5.0)) == "5") }
    @Test func sDoubleFractional() { #expect(R.S(.double(3.14)) == "3.14") }

    @Test func aFlattensNested() {
        let r = R.A([.array([.int(1), .int(2)]), .int(3)])
        #expect(r == [.int(1), .int(2), .int(3)])
    }

    @Test func anCoercesAll() {
        #expect(R.AN([.string("1"), .string("2"), .int(3)]) == [1, 2, 3])
    }

    @Test func asCoercesAll() {
        #expect(R.AS([.int(1), .bool(true), .string("x")]) == ["1", "1", "x"])
    }
}

// MARK: - Logic (F8.4)

@Suite("Runtime logic")
struct TestRuntimeLogic {
    @Test func ifTrue() { #expect(R.IF(.bool(true), .int(1), .int(2)) == .int(1)) }
    @Test func ifFalse() { #expect(R.IF(.bool(false), .int(1), .int(2)) == .int(2)) }
    @Test func ifNilIsFalse() { #expect(R.IF(nil, .int(1), .int(2)) == .int(2)) }
    @Test func isTruthyEmptyString() { #expect(R.isTruthy(.string("")) == false) }
    @Test func isTruthyZero() { #expect(R.isTruthy(.int(0)) == false) }
    @Test func isTruthyPositive() { #expect(R.isTruthy(.int(5)) == true) }
    @Test func blankIsNull() { #expect(R.BLANK() == .null) }
    @Test func iserrorNaN() { #expect(R.ISERROR(.double(.nan)) == .bool(true)) }
    @Test func iserrorNormal() { #expect(R.ISERROR(.int(5)) == .bool(false)) }
}

// MARK: - Math (F8.4)

@Suite("Runtime math")
struct TestRuntimeMath {
    @Test func sumBasic() { #expect(R.SUM(.int(1), .int(2), .int(3)) == .int(6)) }
    @Test func sumWithArray() { #expect(R.SUM(.array([.int(1), .int(2)]), .int(3)) == .int(6)) }
    @Test func averageBasic() { #expect(R.AVERAGE(.int(2), .int(4)) == .int(3)) }
    @Test func minBasic() { #expect(R.MIN(.int(3), .int(1), .int(2)) == .int(1)) }
    @Test func maxBasic() { #expect(R.MAX(.int(3), .int(1), .int(2)) == .int(3)) }
    @Test func countSkipsStrings() { #expect(R.COUNT(.int(1), .string("x"), .int(2)) == .int(2)) }
    @Test func countaSkipsNulls() { #expect(R.COUNTA(.int(1), .null, .string("")) == .int(1)) }

    @Test func roundToInt() { #expect(R.ROUND(.double(3.7), nil) == .int(4)) }
    @Test func roundToPrecision() { #expect(R.ROUND(.double(3.14159), .int(2)) == .double(3.14)) }
    @Test func roundupInt() { #expect(R.ROUNDUP(.double(3.1), nil) == .int(4)) }
    @Test func rounddownInt() { #expect(R.ROUNDDOWN(.double(3.9), nil) == .int(3)) }
    @Test func ceilingBasic() { #expect(R.CEILING(.double(3.2), nil) == .int(4)) }
    @Test func floorBasic() { #expect(R.FLOOR(.double(3.8), nil) == .int(3)) }

    @Test func absNegative() { #expect(R.ABS(.int(-5)) == .int(5)) }
    @Test func absPositive() { #expect(R.ABS(.int(5)) == .int(5)) }
    @Test func sqrtBasic() { #expect(R.SQRT(.int(9)) == .int(3)) }
    @Test func powerBasic() { #expect(R.POWER(.int(2), .int(3)) == .int(8)) }
    @Test func modBasic() { #expect(R.MOD(.int(10), .int(3)) == .int(1)) }
    @Test func modDivZeroIsNaN() {
        if case .double(let d) = R.MOD(.int(5), .int(0)) { #expect(d.isNaN) } else { Issue.record("expected nan") }
    }
    @Test func intTruncates() { #expect(R.INT(.double(3.7)) == .int(3)) }
    @Test func intNegative() { #expect(R.INT(.double(-3.2)) == .int(-4)) }

    @Test func evenRoundsUp() { #expect(R.EVEN(.double(3.0)) == .int(4)) }
    @Test func oddRoundsUp() { #expect(R.ODD(.double(2.0)) == .int(3)) }
    @Test func valueString() { #expect(R.VALUE(.string("42")) == .int(42)) }
    @Test func valueInvalid() {
        if case .double(let d) = R.VALUE(.string("abc")) { #expect(d.isNaN) } else { Issue.record("expected nan") }
    }
}

// MARK: - String (F8.6)

@Suite("Runtime string")
struct TestRuntimeString {
    @Test func lenString() { #expect(R.LEN(.string("hello")) == .int(5)) }
    @Test func leftBasic() { #expect(R.LEFT(.string("hello"), .int(3)) == .string("hel")) }
    @Test func rightBasic() { #expect(R.RIGHT(.string("hello"), .int(3)) == .string("llo")) }
    @Test func midBasic() { #expect(R.MID(.string("hello"), .int(2), .int(3)) == .string("ell")) }
    @Test func findFound() { #expect(R.FIND(.string("l"), .string("hello"), nil) == .int(3)) }
    @Test func findNotFound() { #expect(R.FIND(.string("z"), .string("hello"), nil) == .int(0)) }
    @Test func searchCaseInsensitive() {
        #expect(R.SEARCH(.string("L"), .string("hello"), nil) == .int(3))
    }
    @Test func substituteAll() {
        #expect(R.SUBSTITUTE(.string("a-b-c"), .string("-"), .string("_"), nil) == .string("a_b_c"))
    }
    @Test func substituteNth() {
        #expect(R.SUBSTITUTE(.string("a-b-c"), .string("-"), .string("_"), .int(2)) == .string("a-b_c"))
    }
    @Test func replaceBasic() {
        #expect(R.REPLACE(.string("hello"), .int(2), .int(3), .string("XX")) == .string("hXXo"))
    }
    @Test func lowerBasic() { #expect(R.LOWER(.string("HI")) == .string("hi")) }
    @Test func upperBasic() { #expect(R.UPPER(.string("hi")) == .string("HI")) }
    @Test func trimBasic() { #expect(R.TRIM(.string("  x  ")) == .string("x")) }
    @Test func reptBasic() { #expect(R.REPT(.string("ab"), .int(3)) == .string("ababab")) }
    @Test func concatenateBasic() {
        #expect(R.CONCATENATE(.string("a"), .int(1), .string("b")) == .string("a1b"))
    }
}

// MARK: - Date (F8.7)

@Suite("Runtime date")
struct TestRuntimeDate {
    @Test func yearOfIsoDate() {
        #expect(R.YEAR(.string("2025-04-20T10:00:00Z")) == .int(2025))
    }
    @Test func monthOfIsoDate() {
        #expect(R.MONTH(.string("2025-04-20T10:00:00Z")) == .int(4))
    }
    @Test func dayOfIsoDate() {
        #expect(R.DAY(.string("2025-04-20T10:00:00Z")) == .int(20))
    }
    @Test func hourOfIsoDate() {
        #expect(R.HOUR(.string("2025-04-20T10:30:00Z")) == .int(10))
    }
    @Test func datetimeDiffDays() {
        let a = V.string("2025-04-20T00:00:00Z")
        let b = V.string("2025-04-15T00:00:00Z")
        #expect(R.DATETIME_DIFF(a, b, .string("days")) == .int(5))
    }
    @Test func datetimeDiffHours() {
        let a = V.string("2025-04-20T12:00:00Z")
        let b = V.string("2025-04-20T00:00:00Z")
        #expect(R.DATETIME_DIFF(a, b, .string("hours")) == .int(12))
    }
    @Test func isSameSameDay() {
        let a = V.string("2025-04-20T10:00:00Z")
        let b = V.string("2025-04-20T15:00:00Z")
        #expect(R.IS_SAME(a, b, .string("days")) == .bool(true))
    }
    @Test func isBeforeDay() {
        let a = V.string("2025-04-20T10:00:00Z")
        let b = V.string("2025-04-21T10:00:00Z")
        #expect(R.IS_BEFORE(a, b, .string("days")) == .bool(true))
    }
}

// MARK: - Array (F8.8)

@Suite("Runtime array")
struct TestRuntimeArray {
    @Test func arrayJoinDefault() {
        #expect(R.ARRAYJOIN(.array([.int(1), .int(2), .int(3)]), nil) == .string("1, 2, 3"))
    }
    @Test func arrayJoinCustomSep() {
        #expect(
            R.ARRAYJOIN(.array([.int(1), .int(2)]), .string("-")) == .string("1-2")
        )
    }
    @Test func arrayUniqueBasic() {
        let input = V.array([.int(1), .int(2), .int(1), .int(3)])
        #expect(R.ARRAYUNIQUE(input) == .array([.int(1), .int(2), .int(3)]))
    }
    @Test func arrayCompactStripsNulls() {
        let input = V.array([.int(1), .null, .string(""), .int(2)])
        #expect(R.ARRAYCOMPACT(input) == .array([.int(1), .int(2)]))
    }
    @Test func arrayFlattenNested() {
        let input = V.array([.int(1), .array([.int(2), .int(3)]), .int(4)])
        #expect(R.ARRAYFLATTEN(input) == .array([.int(1), .int(2), .int(3), .int(4)]))
    }
}

// MARK: - Regex (F8.9)

@Suite("Runtime regex")
struct TestRuntimeRegex {
    @Test func regexMatchTrue() {
        #expect(R.REGEX_MATCH(.string("hello"), .string("^hel")) == .bool(true))
    }
    @Test func regexMatchFalse() {
        #expect(R.REGEX_MATCH(.string("hello"), .string("^xyz")) == .bool(false))
    }
    @Test func regexExtractBasic() {
        #expect(R.REGEX_EXTRACT(.string("hello123"), .string("\\d+")) == .string("123"))
    }
    @Test func regexReplaceBasic() {
        #expect(
            R.REGEX_REPLACE(.string("hello"), .string("l+"), .string("x")) == .string("hexo")
        )
    }
}

// myairtable-02fg regression — the emitted equality shapes must EVALUATE
// correctly: AirtableJSONValue enum equality made .double(5.0) != .int(5),
// so =/!= route through N()/S() coercion on both sides.
@Suite("Transpiled equality shapes")
struct TestTranspiledEqualityShapes {
    @Test func numericEqualityShapeIsTrueForWholeNumberFields() {
        #expect(AirtableRuntime.N(AirtableRuntime.V(5.0)) == AirtableRuntime.N(.int(5)))
        #expect(AirtableRuntime.N(AirtableRuntime.V(5)) == AirtableRuntime.N(.int(5)))
        #expect(AirtableRuntime.N(AirtableRuntime.V(4.0)) != AirtableRuntime.N(.int(5)))
    }

    @Test func preFixShapeWasConstantFalse() {
        // Documents the bug the coercion fix removes.
        #expect(AirtableJSONValue.double(5.0) != AirtableJSONValue.int(5))
    }

    @Test func stringEqualityShapeCoercesBothSides() {
        #expect(AirtableRuntime.S(AirtableRuntime.V("hi")) == AirtableRuntime.S(.string("hi")))
        #expect(AirtableRuntime.S(AirtableRuntime.V(5.0)) == AirtableRuntime.S(.int(5)))
    }
}
