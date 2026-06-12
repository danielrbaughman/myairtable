package myairtable

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

// K7.4 — Unit tests for the formula builder DSL. Mirrors
// tests/test_formula.rs and Swift TestFormula.swift (~86 test cases).
// Naming deviation per §2.3.2: `eq` / `neq` instead of `equals` / `notEquals`.

// region Combinators (K7.4)

class TestFormulaCombinators {
    @Test
    fun andCombines() = assertEquals("AND(A,B,C)", Formulas.and("A", "B", "C"))

    @Test
    fun andSingleReturnsBare() = assertEquals("A", Formulas.and("A"))

    @Test
    fun andEmptyReturnsEmpty() = assertEquals("", Formulas.and(emptyList()))

    @Test
    fun andFiltersEmptyStrings() = assertEquals("AND(A,B)", Formulas.and("A", "", "B"))

    @Test
    fun orCombines() = assertEquals("OR(A,B)", Formulas.or("A", "B"))

    @Test
    fun notWraps() = assertEquals("NOT(A)", Formulas.not("A"))

    @Test
    fun xorCombines() = assertEquals("XOR(A,B)", Formulas.xor("A", "B"))

    @Test
    fun xorSingleReturnsBare() = assertEquals("X", Formulas.xor("X"))
}

// endregion

// region Record ID (K7.5)

class TestFormulaId {
    private val f = FormulaId()

    @Test
    fun idEq() = assertEquals("RECORD_ID()='rec123'", f.eq("rec123"))

    @Test
    fun idInListEmpty() = assertEquals("FALSE()", f.inList(emptyList()))

    @Test
    fun idInListSingle() = assertEquals("RECORD_ID()='rec123'", f.inList(listOf("rec123")))

    @Test
    fun idInListMultiple() {
        val r = f.inList(listOf("rec1", "rec2"))
        assertTrue(r.startsWith("OR("))
        assertTrue(r.contains("rec1"))
        assertTrue(r.contains("rec2"))
    }
}

// endregion

// region Text Field (K7.6)

class TestFormulaTextField {
    private val f = FormulaTextField("fld123")

    @Test
    fun eqCaseSensitive() = assertEquals("{fld123}=\"hello\"", f.eq("hello"))

    @Test
    fun eqEscapesQuotes() = assertEquals("{fld123}=\"say \\\"hi\\\"\"", f.eq("say \"hi\""))

    @Test
    fun eqCaseInsensitive() = assertTrue(f.eq("hello", caseSensitive = false).contains("LOWER("))

    @Test
    fun eqWithTrim() = assertTrue(f.eq("hello", trim = true).contains("TRIM("))

    @Test
    fun equalsAnyCombinesWithOr() {
        val r = f.equalsAny(listOf("a", "b"))
        assertTrue(r.startsWith("OR("))
    }

    @Test
    fun neq() = assertEquals("{fld123}!=\"x\"", f.neq("x"))

    @Test
    fun containsSubstring() = assertEquals("FIND(\"ell\",{fld123})>0", f.contains("ell"))

    @Test
    fun containsCaseInsensitive() = assertTrue(f.contains("ell", caseSensitive = false).contains("LOWER("))

    @Test
    fun containsAnyCombinesWithOr() {
        val r = f.containsAny(listOf("a", "b"))
        assertTrue(r.startsWith("OR("))
    }

    @Test
    fun containsAllCombinesWithAnd() {
        val r = f.containsAll(listOf("a", "b"))
        assertTrue(r.startsWith("AND("))
    }

    @Test
    fun notContainsWrapsInNot() {
        val r = f.notContains("x")
        assertTrue(r.startsWith("NOT("))
        assertTrue(r.contains("FIND("))
    }

    @Test
    fun startsWithFind1() = assertEquals("FIND(\"hel\",{fld123})=1", f.startsWith("hel"))

    @Test
    fun notStartsWithFindNot1() = assertEquals("FIND(\"hel\",{fld123})!=1", f.notStartsWith("hel"))

    @Test
    fun endsWithFormula() {
        val r = f.endsWith("lo")
        assertTrue(r.contains("FIND("))
        assertTrue(r.contains("LEN("))
    }

    @Test
    fun notEndsWithFormula() {
        val r = f.notEndsWith("lo")
        assertTrue(r.contains("FIND("))
        assertTrue(r.contains("!=LEN("))
    }

    @Test
    fun phoneEqualsNormalized() {
        val r = f.phoneEquals("+1 (555) 123-4567")
        assertTrue(r.contains("15551234567"))
        assertTrue(r.contains("SUBSTITUTE"))
    }

    @Test
    fun regexMatch() = assertEquals("REGEX_MATCH({fld123},\"^[A-Z]+$\")", f.regexMatch("^[A-Z]+$"))

    @Test
    fun emptyCheck() = assertEquals("{fld123}=BLANK()", f.empty())

    @Test
    fun notEmptyCheck() = assertEquals("{fld123}!=BLANK()", f.notEmpty())

    @Test
    fun eqCaseInsensitiveAndTrim() {
        val r = f.eq("hello", caseSensitive = false, trim = true)
        assertTrue(r.contains("LOWER("))
        assertTrue(r.contains("TRIM("))
    }

    @Test
    fun containsWithTrim() {
        val r = f.contains("ell", trim = true)
        assertTrue(r.contains("TRIM("))
    }

    @Test
    fun neqWithOptions() {
        val r = f.neq("x", caseSensitive = false)
        assertTrue(r.contains("LOWER("))
        assertTrue(r.contains("!="))
    }
}

// endregion

// region Single Select (K7.7)

class TestFormulaSingleSelect {
    private val f = FormulaSingleSelectField("fldSS")

    @Test
    fun selectEq() = assertEquals("{fldSS}=\"Choice 1\"", f.eq("Choice 1"))

    @Test
    fun selectEqualsAny() = assertTrue(f.equalsAny(listOf("A", "B")).startsWith("OR("))

    @Test
    fun selectNeq() = assertEquals("{fldSS}!=\"C\"", f.neq("C"))

    @Test
    fun selectEmpty() = assertEquals("{fldSS}=BLANK()", f.empty())
}

// endregion

// region Multi Select (K7.8)

class TestFormulaMultiSelect {
    private val f = FormulaMultiSelectField("fldMS")

    @Test
    fun multiContains() = assertEquals("FIND(\"opt\",{fldMS})>0", f.contains("opt"))

    @Test
    fun multiContainsAny() = assertTrue(f.containsAny(listOf("a", "b")).startsWith("OR("))

    @Test
    fun multiContainsAll() = assertTrue(f.containsAll(listOf("a", "b")).startsWith("AND("))

    @Test
    fun multiNotContains() = assertTrue(f.notContains("x").startsWith("NOT("))
}

// endregion

// region Number Field (K7.9)

class TestFormulaNumber {
    private val f = FormulaNumberField("fldN")

    @Test
    fun numEq() = assertEquals("{fldN}=42", f.eq(42))

    @Test
    fun numNeq() = assertEquals("{fldN}!=0", f.neq(0))

    @Test
    fun numGreaterThan() = assertEquals("{fldN}>10", f.greaterThan(10))

    @Test
    fun numLessThan() = assertEquals("{fldN}<5", f.lessThan(5))

    @Test
    fun numGte() = assertEquals("{fldN}>=1", f.greaterThanOrEquals(1))

    @Test
    fun numLte() = assertEquals("{fldN}<=99", f.lessThanOrEquals(99))

    @Test
    fun numBetweenInclusive() {
        val r = f.between(1, 10, inclusive = true)
        assertTrue(r.startsWith("AND("))
        assertTrue(r.contains(">="))
        assertTrue(r.contains("<="))
    }

    @Test
    fun numBetweenExclusive() {
        val r = f.between(1, 10, inclusive = false)
        assertTrue(r.contains(">{") || r.contains(">1"))
        assertTrue(r.contains("<{") || r.contains("<10"))
    }

    @Test
    fun numEqFloat() = assertEquals("{fldN}=3.14", f.eq(3.14))

    @Test
    fun numEmpty() = assertEquals("{fldN}=BLANK()", f.empty())
}

// endregion

// region Boolean Field (K7.10)

class TestFormulaBoolean {
    private val f = FormulaBooleanField("fldB")

    @Test
    fun boolIsTrue() = assertEquals("{fldB}=TRUE()", f.isTrue())

    @Test
    fun boolIsFalse() = assertEquals("{fldB}=FALSE()", f.isFalse())

    @Test
    fun boolEqTrue() = assertEquals("{fldB}=TRUE()", f.eq(true))

    @Test
    fun boolEqFalse() = assertEquals("{fldB}=FALSE()", f.eq(false))
}

// endregion

// region Date Field (K7.11)

class TestFormulaDate {
    private val f = FormulaDateField("fldD")

    // Absolute dates

    @Test
    fun onDate() = assertEquals("DATETIME_PARSE('2025-01-15')=DATETIME_PARSE({fldD})", f.on("2025-01-15"))

    @Test
    fun notOnDate() = assertTrue(f.notOn("2025-01-15").contains("!="))

    @Test
    fun afterDate() = assertTrue(f.after("2025-01-15").contains("<"))

    @Test
    fun beforeDate() = assertTrue(f.before("2025-01-15").contains(">"))

    @Test
    fun onOrAfterDate() = assertTrue(f.onOrAfter("2025-01-15").contains("<="))

    @Test
    fun onOrBeforeDate() = assertTrue(f.onOrBefore("2025-01-15").contains(">="))

    @Test
    fun betweenDatesInclusive() {
        val r = f.between("2025-01-01", "2025-12-31", inclusive = true)
        assertTrue(r.startsWith("AND("))
    }

    @Test
    fun betweenDatesExclusive() {
        val r = f.between("2025-01-01", "2025-12-31", inclusive = false)
        assertTrue(r.startsWith("AND("))
    }

    @Test
    fun dateEmpty() = assertEquals("{fldD}=BLANK()", f.empty())

    @Test
    fun dateNotEmpty() = assertEquals("{fldD}!=BLANK()", f.notEmpty())

    // Time-ago chaining

    @Test
    fun daysAgo() {
        val r = f.after().daysAgo(7)
        assertTrue(r.contains("DATETIME_DIFF(NOW()"))
        assertTrue(r.contains("\"days\""))
        assertTrue(r.contains("<7"))
    }

    @Test
    fun yearsAgo() {
        val r = f.before().yearsAgo(1)
        assertTrue(r.contains("\"years\""))
    }

    @Test
    fun weeksAgo() {
        val r = f.on().weeksAgo(2)
        assertTrue(r.contains("\"weeks\""))
        assertTrue(r.contains("=2"))
    }

    @Test
    fun hoursAgo() = assertTrue(f.after().hoursAgo(24).contains("\"hours\""))

    @Test
    fun minutesAgo() = assertTrue(f.after().minutesAgo(30).contains("\"minutes\""))

    @Test
    fun secondsAgo() = assertTrue(f.after().secondsAgo(60).contains("\"seconds\""))

    @Test
    fun monthsAgo() = assertTrue(f.before().monthsAgo(3).contains("\"months\""))

    @Test
    fun quartersAgo() = assertTrue(f.before().quartersAgo(2).contains("\"quarters\""))

    @Test
    fun millisecondsAgo() = assertTrue(f.after().millisecondsAgo(500).contains("\"milliseconds\""))

    @Test
    fun onOrAfterChainDays() {
        val r = f.onOrAfter().daysAgo(30)
        assertTrue(r.contains("<="))
    }

    @Test
    fun onOrBeforeChainDays() {
        val r = f.onOrBefore().daysAgo(30)
        assertTrue(r.contains(">="))
    }

    @Test
    fun notOnChainDays() {
        val r = f.notOn().daysAgo(1)
        assertTrue(r.contains("!="))
    }

    @Test
    fun onChainYears() {
        val r = f.on().yearsAgo(5)
        assertTrue(r.contains("=5"))
    }
}

// endregion

// region Attachment Field (K7.12)

class TestFormulaAttachment {
    private val f = FormulaAttachmentsField("fldA")

    @Test
    fun attachmentEmpty() = assertEquals("LEN({fldA})=0", f.empty())

    @Test
    fun attachmentNotEmpty() = assertEquals("LEN({fldA})>0", f.notEmpty())

    @Test
    fun attachmentCount() = assertEquals("LEN({fldA})=3", f.count(3))
}

// endregion

// region Lookup Field (parity with tests/test_formula.rs lookup_* tests)

class TestFormulaLookup {
    private val f = FormulaLookupField("fldClient")

    @Test
    fun containsWrapsInArrayjoin() {
        val r = f.contains("groundwork", caseSensitive = false, trim = true)
        assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: $r")
        assertTrue(r.contains("FIND("), "missing FIND: $r")
        assertTrue(r.contains("LOWER("), "missing LOWER: $r")
    }

    @Test
    fun startsWithWrapsInArrayjoin() {
        val r = f.startsWith("Ground", caseSensitive = false, trim = true)
        assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: $r")
    }

    @Test
    fun endsWithWrapsInArrayjoin() {
        val r = f.endsWith("BioAg", caseSensitive = false, trim = true)
        assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: $r")
        assertTrue(r.contains("LEN("), "missing LEN: $r")
    }

    @Test
    fun eqDoesNotWrapInArrayjoin() {
        // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
        val r = f.eq("Groundwork Bio Ag")
        assertFalse(r.contains("ARRAYJOIN"), "should not wrap eq: $r")
        assertTrue(r.contains("{fldClient}"), "missing field: $r")
    }

    @Test
    fun notEmptyDoesNotWrap() = assertFalse(f.notEmpty().contains("ARRAYJOIN"))

    @Test
    fun textFieldUnaffectedRegression() {
        // Regression: FormulaTextField must still emit a bare {field} reference.
        val t = FormulaTextField("fldName")
        assertFalse(t.contains("hello", caseSensitive = false, trim = true).contains("ARRAYJOIN"))
    }
}

// endregion

// region Date field-to-field comparisons

class TestFormulaDateFieldOperand {
    private val f = FormulaDateField("fld123")
    private val other = FormulaDateField("fldOther")

    @Test
    fun onAnotherField() = assertEquals("DATETIME_PARSE({fldOther})=DATETIME_PARSE({fld123})", f.on(other))

    @Test
    fun afterAnotherField() = assertTrue(f.after(other).contains("DATETIME_PARSE({fldOther})<DATETIME_PARSE({fld123})"))

    @Test
    fun betweenMixedOperands() {
        val r = f.between("2025-01-01", other)
        assertTrue(r.startsWith("AND("))
        assertTrue(r.contains("DATETIME_PARSE('2025-01-01')"))
        assertTrue(r.contains("DATETIME_PARSE({fldOther})"))
    }

    @Test
    fun stringLiteralStillWorks() {
        val r = f.on("2025-01-15")
        assertTrue(r.contains("DATETIME_PARSE('2025-01-15')"))
        assertTrue(r.contains("=DATETIME_PARSE({fld123})"))
    }
}

// endregion

/**
 * myairtable-53ip — formula-string injection hardening. A value may not break
 * out of its quoted context regardless of embedded quotes/backslashes.
 */
class TestFormulaEscaping {
    private val text = FormulaTextField("fldT")
    private val id = FormulaId()

    @Test
    fun quoteInValueStaysInsideTheString() {
        assertEquals("""{fldT}="a \"quoted\" b"""", text.eq("a \"quoted\" b"))
    }

    @Test
    fun trailingBackslashCannotEscapeTheClosingQuote() {
        // Pre-fix: ...="x\" left the quote live and leaked formula code.
        assertEquals("""{fldT}="x\\"""", text.eq("x\\"))
    }

    @Test
    fun backslashThenQuotePayloadIsNeutralized() {
        val evil = "x\\\", TRUE(), \""
        val formula = text.eq(evil)
        // Every backslash doubled, every quote escaped — the payload cannot
        // terminate the string literal. (Built programmatically: nested-quote
        // raw strings are unreadable here.)
        val expected = "{fldT}=\"" + escapeFormulaString(evil) + "\""
        assertEquals(expected, formula)
        assertEquals("x\\\\\\\", TRUE(), \\\"", escapeFormulaString(evil))
    }

    @Test
    fun recordIdSingleQuoteIsEscaped() {
        assertEquals("""RECORD_ID()='rec\' OR TRUE() OR \''""", id.eq("rec' OR TRUE() OR '"))
    }

    @Test
    fun regexBackslashSurvivesRoundTrip() {
        // \d in the pattern -> \\d in formula source; Airtable's string parser
        // unescapes it back to \d for the regex engine.
        assertEquals("""REGEX_MATCH({fldT},"\\d+")""", text.regexMatch("\\d+"))
    }

    @Test
    fun phoneEqualsEscapesResidualQuotes() {
        val formula = text.phoneEquals("555\"1234")
        assertTrue(formula.endsWith("=\"555\\\"1234\""), formula)
    }
}
