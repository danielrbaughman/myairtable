// F7.4–F7.12 — Unit tests for the formula builder DSL. Mirrors
// tests/test_formula.rs (~86 test cases).

import Foundation
import Testing

@testable import MyAirtableStatic

// MARK: - Combinators (F7.4)

@Suite("Formula Combinators")
struct TestFormulaCombinators {
    @Test func andCombines() { #expect(Formulas.and("A", "B", "C") == "AND(A,B,C)") }
    @Test func andSingleReturnsBare() { #expect(Formulas.and("A") == "A") }
    @Test func andEmptyReturnsEmpty() { #expect(Formulas.and([String]()) == "") }
    @Test func andFiltersEmptyStrings() { #expect(Formulas.and("A", "", "B") == "AND(A,B)") }
    @Test func orCombines() { #expect(Formulas.or("A", "B") == "OR(A,B)") }
    @Test func notWraps() { #expect(Formulas.not("A") == "NOT(A)") }
    @Test func xorCombines() { #expect(Formulas.xor("A", "B") == "XOR(A,B)") }
    @Test func xorSingleReturnsBare() { #expect(Formulas.xor("X") == "X") }
}

// MARK: - Record ID (F7.5)

@Suite("Formula Record ID")
struct TestFormulaId {
    let f = FormulaId()

    @Test func idEquals() { #expect(f.equals("rec123") == "RECORD_ID()='rec123'") }
    @Test func idInListEmpty() { #expect(f.inList([]) == "FALSE()") }
    @Test func idInListSingle() { #expect(f.inList(["rec123"]) == "RECORD_ID()='rec123'") }
    @Test func idInListMultiple() {
        let r = f.inList(["rec1", "rec2"])
        #expect(r.hasPrefix("OR("))
        #expect(r.contains("rec1"))
        #expect(r.contains("rec2"))
    }
}

// MARK: - Text Field (F7.6)

@Suite("Formula Text Field")
struct TestFormulaTextField {
    let f = FormulaTextField("fld123")

    @Test func equalsCaseSensitive() { #expect(f.equals("hello") == "{fld123}=\"hello\"") }
    @Test func equalsEscapesQuotes() { #expect(f.equals("say \"hi\"") == "{fld123}=\"say \\\"hi\\\"\"") }
    @Test func equalsCaseInsensitive() { #expect(f.equals("hello", caseSensitive: false).contains("LOWER(")) }
    @Test func equalsWithTrim() { #expect(f.equals("hello", trim: true).contains("TRIM(")) }
    @Test func equalsAnyCombinesWithOr() {
        let r = f.equalsAny(["a", "b"])
        #expect(r.hasPrefix("OR("))
    }
    @Test func notEquals() { #expect(f.notEquals("x") == "{fld123}!=\"x\"") }
    @Test func containsSubstring() { #expect(f.contains("ell") == "FIND(\"ell\",{fld123})>0") }
    @Test func containsCaseInsensitive() { #expect(f.contains("ell", caseSensitive: false).contains("LOWER(")) }
    @Test func containsAnyCombinesWithOr() {
        let r = f.containsAny(["a", "b"])
        #expect(r.hasPrefix("OR("))
    }
    @Test func containsAllCombinesWithAnd() {
        let r = f.containsAll(["a", "b"])
        #expect(r.hasPrefix("AND("))
    }
    @Test func notContainsWrapsInNot() {
        let r = f.notContains("x")
        #expect(r.hasPrefix("NOT("))
        #expect(r.contains("FIND("))
    }
    @Test func startsWithFind1() { #expect(f.startsWith("hel") == "FIND(\"hel\",{fld123})=1") }
    @Test func notStartsWithFindNot1() {
        #expect(f.notStartsWith("hel") == "FIND(\"hel\",{fld123})!=1")
    }
    @Test func endsWithFormula() {
        let r = f.endsWith("lo")
        #expect(r.contains("FIND("))
        #expect(r.contains("LEN("))
    }
    @Test func notEndsWithFormula() {
        let r = f.notEndsWith("lo")
        #expect(r.contains("FIND("))
        #expect(r.contains("!=LEN("))
    }
    @Test func phoneEqualsNormalized() {
        let r = f.phoneEquals("+1 (555) 123-4567")
        #expect(r.contains("15551234567"))
        #expect(r.contains("SUBSTITUTE"))
    }
    @Test func regexMatch() {
        #expect(f.regexMatch("^[A-Z]+$") == "REGEX_MATCH({fld123},\"^[A-Z]+$\")")
    }
    @Test func emptyCheck() { #expect(f.empty() == "{fld123}=BLANK()") }
    @Test func notEmptyCheck() { #expect(f.notEmpty() == "{fld123}!=BLANK()") }
    @Test func equalsCaseInsensitiveAndTrim() {
        let r = f.equals("hello", caseSensitive: false, trim: true)
        #expect(r.contains("LOWER("))
        #expect(r.contains("TRIM("))
    }
    @Test func containsWithTrim() {
        let r = f.contains("ell", trim: true)
        #expect(r.contains("TRIM("))
    }
    @Test func notEqualsWithOptions() {
        let r = f.notEquals("x", caseSensitive: false)
        #expect(r.contains("LOWER("))
        #expect(r.contains("!="))
    }
}

// MARK: - Single Select (F7.7)

@Suite("Formula Single Select")
struct TestFormulaSingleSelect {
    let f = FormulaSingleSelectField("fldSS")

    @Test func selectEquals() { #expect(f.equals("Choice 1") == "{fldSS}=\"Choice 1\"") }
    @Test func selectEqualsAny() { #expect(f.equalsAny(["A", "B"]).hasPrefix("OR(")) }
    @Test func selectNotEquals() { #expect(f.notEquals("C") == "{fldSS}!=\"C\"") }
    @Test func selectEmpty() { #expect(f.empty() == "{fldSS}=BLANK()") }
}

// MARK: - Multi Select (F7.8)

@Suite("Formula Multi Select")
struct TestFormulaMultiSelect {
    let f = FormulaMultiSelectField("fldMS")

    @Test func multiContains() { #expect(f.contains("opt") == "FIND(\"opt\",{fldMS})>0") }
    @Test func multiContainsAny() { #expect(f.containsAny(["a", "b"]).hasPrefix("OR(")) }
    @Test func multiContainsAll() { #expect(f.containsAll(["a", "b"]).hasPrefix("AND(")) }
    @Test func multiNotContains() { #expect(f.notContains("x").hasPrefix("NOT(")) }
}

// MARK: - Number Field (F7.9)

@Suite("Formula Number Field")
struct TestFormulaNumber {
    let f = FormulaNumberField("fldN")

    @Test func numEquals() { #expect(f.equals(42) == "{fldN}=42") }
    @Test func numNotEquals() { #expect(f.notEquals(0) == "{fldN}!=0") }
    @Test func numGreaterThan() { #expect(f.greaterThan(10) == "{fldN}>10") }
    @Test func numLessThan() { #expect(f.lessThan(5) == "{fldN}<5") }
    @Test func numGte() { #expect(f.greaterThanOrEquals(1) == "{fldN}>=1") }
    @Test func numLte() { #expect(f.lessThanOrEquals(99) == "{fldN}<=99") }
    @Test func numBetweenInclusive() {
        let r = f.between(1, 10, inclusive: true)
        #expect(r.hasPrefix("AND("))
        #expect(r.contains(">="))
        #expect(r.contains("<="))
    }
    @Test func numBetweenExclusive() {
        let r = f.between(1, 10, inclusive: false)
        #expect(r.contains(">{") || r.contains(">1"))
        #expect(r.contains("<{") || r.contains("<10"))
    }
    @Test func numEqualsFloat() { #expect(f.equals(3.14) == "{fldN}=3.14") }
    @Test func numEmpty() { #expect(f.empty() == "{fldN}=BLANK()") }
}

// MARK: - Boolean Field (F7.10)

@Suite("Formula Boolean Field")
struct TestFormulaBoolean {
    let f = FormulaBooleanField("fldB")

    @Test func boolIsTrue() { #expect(f.isTrue() == "{fldB}=TRUE()") }
    @Test func boolIsFalse() { #expect(f.isFalse() == "{fldB}=FALSE()") }
    @Test func boolEqualsTrue() { #expect(f.equals(true) == "{fldB}=TRUE()") }
    @Test func boolEqualsFalse() { #expect(f.equals(false) == "{fldB}=FALSE()") }
}

// MARK: - Date Field (F7.11)

@Suite("Formula Date Field")
struct TestFormulaDate {
    let f = FormulaDateField("fldD")

    // Absolute dates
    @Test func onDate() {
        #expect(f.on("2025-01-15") == "DATETIME_PARSE('2025-01-15')=DATETIME_PARSE({fldD})")
    }
    @Test func notOnDate() { #expect(f.notOn("2025-01-15").contains("!=")) }
    @Test func afterDate() { #expect(f.after("2025-01-15").contains("<")) }
    @Test func beforeDate() { #expect(f.before("2025-01-15").contains(">")) }
    @Test func onOrAfterDate() { #expect(f.onOrAfter("2025-01-15").contains("<=")) }
    @Test func onOrBeforeDate() { #expect(f.onOrBefore("2025-01-15").contains(">=")) }
    @Test func betweenDatesInclusive() {
        let r = f.between("2025-01-01", "2025-12-31", inclusive: true)
        #expect(r.hasPrefix("AND("))
    }
    @Test func betweenDatesExclusive() {
        let r = f.between("2025-01-01", "2025-12-31", inclusive: false)
        #expect(r.hasPrefix("AND("))
    }
    @Test func dateEmpty() { #expect(f.empty() == "{fldD}=BLANK()") }
    @Test func dateNotEmpty() { #expect(f.notEmpty() == "{fldD}!=BLANK()") }

    // Time-ago chaining
    @Test func daysAgo() {
        let r = f.after().daysAgo(7)
        #expect(r.contains("DATETIME_DIFF(NOW()"))
        #expect(r.contains("\"days\""))
        #expect(r.contains("<7"))
    }
    @Test func yearsAgo() {
        let r = f.before().yearsAgo(1)
        #expect(r.contains("\"years\""))
    }
    @Test func weeksAgo() {
        let r = f.on().weeksAgo(2)
        #expect(r.contains("\"weeks\""))
        #expect(r.contains("=2"))
    }
    @Test func hoursAgo() { #expect(f.after().hoursAgo(24).contains("\"hours\"")) }
    @Test func minutesAgo() { #expect(f.after().minutesAgo(30).contains("\"minutes\"")) }
    @Test func secondsAgo() { #expect(f.after().secondsAgo(60).contains("\"seconds\"")) }
    @Test func monthsAgo() { #expect(f.before().monthsAgo(3).contains("\"months\"")) }
    @Test func quartersAgo() { #expect(f.before().quartersAgo(2).contains("\"quarters\"")) }
    @Test func millisecondsAgo() { #expect(f.after().millisecondsAgo(500).contains("\"milliseconds\"")) }
    @Test func onOrAfterChainDays() {
        let r = f.onOrAfter().daysAgo(30)
        #expect(r.contains("<="))
    }
    @Test func onOrBeforeChainDays() {
        let r = f.onOrBefore().daysAgo(30)
        #expect(r.contains(">="))
    }
    @Test func notOnChainDays() {
        let r = f.notOn().daysAgo(1)
        #expect(r.contains("!="))
    }
    @Test func onChainYears() {
        let r = f.on().yearsAgo(5)
        #expect(r.contains("=5"))
    }
}

// MARK: - Attachment Field (F7.12)

@Suite("Formula Attachment Field")
struct TestFormulaAttachment {
    let f = FormulaAttachmentsField("fldA")

    @Test func attachmentEmpty() { #expect(f.empty() == "LEN({fldA})=0") }
    @Test func attachmentNotEmpty() { #expect(f.notEmpty() == "LEN({fldA})>0") }
    @Test func attachmentCount() { #expect(f.count(3) == "LEN({fldA})=3") }
}

// MARK: - Lookup Field (parity with tests/test_formula.rs lookup_* tests)

@Suite("Formula Lookup Field")
struct TestFormulaLookup {
    let f = FormulaLookupField("fldClient")

    @Test func containsWrapsInArrayjoin() {
        let r = f.contains("groundwork", caseSensitive: false, trim: true)
        #expect(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: \(r)")
        #expect(r.contains("FIND("), "missing FIND: \(r)")
        #expect(r.contains("LOWER("), "missing LOWER: \(r)")
    }

    @Test func startsWithWrapsInArrayjoin() {
        let r = f.startsWith("Ground", caseSensitive: false, trim: true)
        #expect(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: \(r)")
    }

    @Test func endsWithWrapsInArrayjoin() {
        let r = f.endsWith("BioAg", caseSensitive: false, trim: true)
        #expect(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: \(r)")
        #expect(r.contains("LEN("), "missing LEN: \(r)")
    }

    @Test func equalsDoesNotWrapInArrayjoin() {
        // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
        let r = f.equals("Groundwork Bio Ag")
        #expect(!r.contains("ARRAYJOIN"), "should not wrap equals: \(r)")
        #expect(r.contains("{fldClient}"), "missing field: \(r)")
    }

    @Test func notEmptyDoesNotWrap() {
        #expect(!f.notEmpty().contains("ARRAYJOIN"))
    }

    @Test func textFieldUnaffectedRegression() {
        // Regression: FormulaTextField must still emit a bare {field} reference.
        let t = FormulaTextField("fldName")
        #expect(!t.contains("hello", caseSensitive: false, trim: true).contains("ARRAYJOIN"))
    }
}

// MARK: - Date field-to-field comparisons

@Suite("Formula Date field operand")
struct TestFormulaDateFieldOperand {
    let f = FormulaDateField("fld123")
    let other = FormulaDateField("fldOther")

    @Test func onAnotherField() {
        let r = f.on(other)
        #expect(r == "DATETIME_PARSE({fldOther})=DATETIME_PARSE({fld123})")
    }

    @Test func afterAnotherField() {
        #expect(f.after(other).contains("DATETIME_PARSE({fldOther})<DATETIME_PARSE({fld123})"))
    }

    @Test func betweenMixedOperands() {
        let r = f.between("2025-01-01", other)
        #expect(r.hasPrefix("AND("))
        #expect(r.contains("DATETIME_PARSE('2025-01-01')"))
        #expect(r.contains("DATETIME_PARSE({fldOther})"))
    }

    @Test func stringLiteralStillWorks() {
        let r = f.on("2025-01-15")
        #expect(r.contains("DATETIME_PARSE('2025-01-15')"))
        #expect(r.contains("=DATETIME_PARSE({fld123})"))
    }
}

// myairtable-53ip — formula-string injection hardening (parity with Kotlin
// TestFormulaEscaping). A value may not break out of its quoted context.
@Suite("Formula escaping")
struct TestFormulaEscaping {
    private let text = FormulaTextField("fldT")
    private let id = FormulaId()

    @Test func quoteInValueStaysInsideTheString() {
        #expect(text.equals("a \"quoted\" b") == #"{fldT}="a \"quoted\" b""#)
    }

    @Test func trailingBackslashCannotEscapeTheClosingQuote() {
        #expect(text.equals("x\\") == #"{fldT}="x\\""#)
    }

    @Test func backslashThenQuotePayloadIsNeutralized() {
        let evil = "x\\\", TRUE(), \""
        let expected = "{fldT}=\"" + escapeFormulaString(evil) + "\""
        #expect(text.equals(evil) == expected)
        #expect(escapeFormulaString(evil) == "x\\\\\\\", TRUE(), \\\"")
    }

    @Test func recordIdSingleQuoteIsEscaped() {
        #expect(id.equals("rec' OR TRUE() OR '") == #"RECORD_ID()='rec\' OR TRUE() OR \''"#)
    }

    @Test func regexBackslashSurvivesRoundTrip() {
        #expect(text.regexMatch("\\d+") == #"REGEX_MATCH({fldT},"\\d+")"#)
    }
}
