package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

// J7.4 — Unit tests for the formula builder DSL. Mirrors Kotlin TestFormula.kt /
// tests/test_formula.rs / Swift TestFormula.swift (~98 test cases).
// Naming deviation per java-plan-v2 §2.3.2: `eq` / `neq` instead of `equals` / `notEquals`.
class TestFormula {

  // region Combinators

  @Nested
  class Combinators {
    @Test
    void andCombines() {
      assertEquals("AND(A,B,C)", Formulas.and("A", "B", "C"));
    }

    @Test
    void andSingleReturnsBare() {
      assertEquals("A", Formulas.and("A"));
    }

    @Test
    void andEmptyReturnsEmpty() {
      assertEquals("", Formulas.and(List.of()));
    }

    @Test
    void andFiltersEmptyStrings() {
      assertEquals("AND(A,B)", Formulas.and("A", "", "B"));
    }

    @Test
    void orCombines() {
      assertEquals("OR(A,B)", Formulas.or("A", "B"));
    }

    @Test
    void notWraps() {
      assertEquals("NOT(A)", Formulas.not("A"));
    }

    @Test
    void xorCombines() {
      assertEquals("XOR(A,B)", Formulas.xor("A", "B"));
    }

    @Test
    void xorSingleReturnsBare() {
      assertEquals("X", Formulas.xor("X"));
    }
  }

  // endregion

  // region Record ID

  @Nested
  class Id {
    private final FormulaId f = new FormulaId();

    @Test
    void idEq() {
      assertEquals("RECORD_ID()='rec123'", f.eq("rec123"));
    }

    @Test
    void idInListEmpty() {
      assertEquals("FALSE()", f.inList(List.of()));
    }

    @Test
    void idInListSingle() {
      assertEquals("RECORD_ID()='rec123'", f.inList(List.of("rec123")));
    }

    @Test
    void idInListMultiple() {
      String r = f.inList(List.of("rec1", "rec2"));
      assertTrue(r.startsWith("OR("));
      assertTrue(r.contains("rec1"));
      assertTrue(r.contains("rec2"));
    }
  }

  // endregion

  // region Text Field

  @Nested
  class TextField {
    private final FormulaTextField f = new FormulaTextField("fld123");

    @Test
    void eqCaseSensitive() {
      assertEquals("{fld123}=\"hello\"", f.eq("hello"));
    }

    @Test
    void eqEscapesQuotes() {
      assertEquals("{fld123}=\"say \\\"hi\\\"\"", f.eq("say \"hi\""));
    }

    @Test
    void eqCaseInsensitive() {
      assertTrue(f.eq("hello", false).contains("LOWER("));
    }

    @Test
    void eqWithTrim() {
      assertTrue(f.eq("hello", true, true).contains("TRIM("));
    }

    @Test
    void equalsAnyCombinesWithOr() {
      String r = f.equalsAny(List.of("a", "b"));
      assertTrue(r.startsWith("OR("));
    }

    @Test
    void neq() {
      assertEquals("{fld123}!=\"x\"", f.neq("x"));
    }

    @Test
    void containsSubstring() {
      assertEquals("FIND(\"ell\",{fld123})>0", f.contains("ell"));
    }

    @Test
    void containsCaseInsensitive() {
      assertTrue(f.contains("ell", false).contains("LOWER("));
    }

    @Test
    void containsAnyCombinesWithOr() {
      String r = f.containsAny(List.of("a", "b"));
      assertTrue(r.startsWith("OR("));
    }

    @Test
    void containsAllCombinesWithAnd() {
      String r = f.containsAll(List.of("a", "b"));
      assertTrue(r.startsWith("AND("));
    }

    @Test
    void notContainsWrapsInNot() {
      String r = f.notContains("x");
      assertTrue(r.startsWith("NOT("));
      assertTrue(r.contains("FIND("));
    }

    @Test
    void startsWithFind1() {
      assertEquals("FIND(\"hel\",{fld123})=1", f.startsWith("hel"));
    }

    @Test
    void notStartsWithFindNot1() {
      assertEquals("FIND(\"hel\",{fld123})!=1", f.notStartsWith("hel"));
    }

    @Test
    void endsWithFormula() {
      String r = f.endsWith("lo");
      assertTrue(r.contains("FIND("));
      assertTrue(r.contains("LEN("));
    }

    @Test
    void notEndsWithFormula() {
      String r = f.notEndsWith("lo");
      assertTrue(r.contains("FIND("));
      assertTrue(r.contains("!=LEN("));
    }

    @Test
    void phoneEqualsNormalized() {
      String r = f.phoneEquals("+1 (555) 123-4567");
      assertTrue(r.contains("15551234567"));
      assertTrue(r.contains("SUBSTITUTE"));
    }

    @Test
    void regexMatch() {
      assertEquals("REGEX_MATCH({fld123},\"^[A-Z]+$\")", f.regexMatch("^[A-Z]+$"));
    }

    @Test
    void emptyCheck() {
      assertEquals("{fld123}=BLANK()", f.empty());
    }

    @Test
    void notEmptyCheck() {
      assertEquals("{fld123}!=BLANK()", f.notEmpty());
    }

    @Test
    void eqCaseInsensitiveAndTrim() {
      String r = f.eq("hello", false, true);
      assertTrue(r.contains("LOWER("));
      assertTrue(r.contains("TRIM("));
    }

    @Test
    void containsWithTrim() {
      String r = f.contains("ell", true, true);
      assertTrue(r.contains("TRIM("));
    }

    @Test
    void neqWithOptions() {
      String r = f.neq("x", false);
      assertTrue(r.contains("LOWER("));
      assertTrue(r.contains("!="));
    }
  }

  // endregion

  // region Single Select

  @Nested
  class SingleSelect {
    private final FormulaSingleSelectField f = new FormulaSingleSelectField("fldSS");

    @Test
    void selectEq() {
      assertEquals("{fldSS}=\"Choice 1\"", f.eq("Choice 1"));
    }

    @Test
    void selectEqualsAny() {
      assertTrue(f.equalsAny(List.of("A", "B")).startsWith("OR("));
    }

    @Test
    void selectNeq() {
      assertEquals("{fldSS}!=\"C\"", f.neq("C"));
    }

    @Test
    void selectEmpty() {
      assertEquals("{fldSS}=BLANK()", f.empty());
    }
  }

  // endregion

  // region Multi Select

  @Nested
  class MultiSelect {
    private final FormulaMultiSelectField f = new FormulaMultiSelectField("fldMS");

    @Test
    void multiContains() {
      assertEquals("FIND(\"opt\",{fldMS})>0", f.contains("opt"));
    }

    @Test
    void multiContainsAny() {
      assertTrue(f.containsAny(List.of("a", "b")).startsWith("OR("));
    }

    @Test
    void multiContainsAll() {
      assertTrue(f.containsAll(List.of("a", "b")).startsWith("AND("));
    }

    @Test
    void multiNotContains() {
      assertTrue(f.notContains("x").startsWith("NOT("));
    }
  }

  // endregion

  // region Number Field

  @Nested
  class NumberField {
    private final FormulaNumberField f = new FormulaNumberField("fldN");

    @Test
    void numEq() {
      assertEquals("{fldN}=42", f.eq(42));
    }

    @Test
    void numNeq() {
      assertEquals("{fldN}!=0", f.neq(0));
    }

    @Test
    void numGreaterThan() {
      assertEquals("{fldN}>10", f.greaterThan(10));
    }

    @Test
    void numLessThan() {
      assertEquals("{fldN}<5", f.lessThan(5));
    }

    @Test
    void numGte() {
      assertEquals("{fldN}>=1", f.greaterThanOrEquals(1));
    }

    @Test
    void numLte() {
      assertEquals("{fldN}<=99", f.lessThanOrEquals(99));
    }

    @Test
    void numBetweenInclusive() {
      String r = f.between(1, 10, true);
      assertTrue(r.startsWith("AND("));
      assertTrue(r.contains(">="));
      assertTrue(r.contains("<="));
    }

    @Test
    void numBetweenExclusive() {
      String r = f.between(1, 10, false);
      assertTrue(r.contains(">{") || r.contains(">1"));
      assertTrue(r.contains("<{") || r.contains("<10"));
    }

    @Test
    void numEqFloat() {
      assertEquals("{fldN}=3.14", f.eq(3.14));
    }

    @Test
    void numEmpty() {
      assertEquals("{fldN}=BLANK()", f.empty());
    }
  }

  // endregion

  // region Boolean Field

  @Nested
  class BooleanField {
    private final FormulaBooleanField f = new FormulaBooleanField("fldB");

    @Test
    void boolIsTrue() {
      assertEquals("{fldB}=TRUE()", f.isTrue());
    }

    @Test
    void boolIsFalse() {
      assertEquals("{fldB}=FALSE()", f.isFalse());
    }

    @Test
    void boolEqTrue() {
      assertEquals("{fldB}=TRUE()", f.eq(true));
    }

    @Test
    void boolEqFalse() {
      assertEquals("{fldB}=FALSE()", f.eq(false));
    }
  }

  // endregion

  // region Date Field

  @Nested
  class DateField {
    private final FormulaDateField f = new FormulaDateField("fldD");

    // Absolute dates

    @Test
    void onDate() {
      assertEquals("DATETIME_PARSE('2025-01-15')=DATETIME_PARSE({fldD})", f.on("2025-01-15"));
    }

    @Test
    void notOnDate() {
      assertTrue(f.notOn("2025-01-15").contains("!="));
    }

    @Test
    void afterDate() {
      assertTrue(f.after("2025-01-15").contains("<"));
    }

    @Test
    void beforeDate() {
      assertTrue(f.before("2025-01-15").contains(">"));
    }

    @Test
    void onOrAfterDate() {
      assertTrue(f.onOrAfter("2025-01-15").contains("<="));
    }

    @Test
    void onOrBeforeDate() {
      assertTrue(f.onOrBefore("2025-01-15").contains(">="));
    }

    @Test
    void betweenDatesInclusive() {
      String r = f.between("2025-01-01", "2025-12-31", true);
      assertTrue(r.startsWith("AND("));
    }

    @Test
    void betweenDatesExclusive() {
      String r = f.between("2025-01-01", "2025-12-31", false);
      assertTrue(r.startsWith("AND("));
    }

    @Test
    void dateEmpty() {
      assertEquals("{fldD}=BLANK()", f.empty());
    }

    @Test
    void dateNotEmpty() {
      assertEquals("{fldD}!=BLANK()", f.notEmpty());
    }

    // Time-ago chaining

    @Test
    void daysAgo() {
      String r = f.after().daysAgo(7);
      assertTrue(r.contains("DATETIME_DIFF(NOW()"));
      assertTrue(r.contains("\"days\""));
      assertTrue(r.contains("<7"));
    }

    @Test
    void yearsAgo() {
      String r = f.before().yearsAgo(1);
      assertTrue(r.contains("\"years\""));
    }

    @Test
    void weeksAgo() {
      String r = f.on().weeksAgo(2);
      assertTrue(r.contains("\"weeks\""));
      assertTrue(r.contains("=2"));
    }

    @Test
    void hoursAgo() {
      assertTrue(f.after().hoursAgo(24).contains("\"hours\""));
    }

    @Test
    void minutesAgo() {
      assertTrue(f.after().minutesAgo(30).contains("\"minutes\""));
    }

    @Test
    void secondsAgo() {
      assertTrue(f.after().secondsAgo(60).contains("\"seconds\""));
    }

    @Test
    void monthsAgo() {
      assertTrue(f.before().monthsAgo(3).contains("\"months\""));
    }

    @Test
    void quartersAgo() {
      assertTrue(f.before().quartersAgo(2).contains("\"quarters\""));
    }

    @Test
    void millisecondsAgo() {
      assertTrue(f.after().millisecondsAgo(500).contains("\"milliseconds\""));
    }

    @Test
    void onOrAfterChainDays() {
      String r = f.onOrAfter().daysAgo(30);
      assertTrue(r.contains("<="));
    }

    @Test
    void onOrBeforeChainDays() {
      String r = f.onOrBefore().daysAgo(30);
      assertTrue(r.contains(">="));
    }

    @Test
    void notOnChainDays() {
      String r = f.notOn().daysAgo(1);
      assertTrue(r.contains("!="));
    }

    @Test
    void onChainYears() {
      String r = f.on().yearsAgo(5);
      assertTrue(r.contains("=5"));
    }
  }

  // endregion

  // region Attachment Field

  @Nested
  class AttachmentField {
    private final FormulaAttachmentsField f = new FormulaAttachmentsField("fldA");

    @Test
    void attachmentEmpty() {
      assertEquals("LEN({fldA})=0", f.empty());
    }

    @Test
    void attachmentNotEmpty() {
      assertEquals("LEN({fldA})>0", f.notEmpty());
    }

    @Test
    void attachmentCount() {
      assertEquals("LEN({fldA})=3", f.count(3));
    }
  }

  // endregion

  // region Lookup Field (parity with tests/test_formula.rs lookup_* tests)

  @Nested
  class LookupField {
    private final FormulaLookupField f = new FormulaLookupField("fldClient");

    @Test
    void containsWrapsInArrayjoin() {
      String r = f.contains("groundwork", false, true);
      assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: " + r);
      assertTrue(r.contains("FIND("), "missing FIND: " + r);
      assertTrue(r.contains("LOWER("), "missing LOWER: " + r);
    }

    @Test
    void startsWithWrapsInArrayjoin() {
      String r = f.startsWith("Ground", false, true);
      assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: " + r);
    }

    @Test
    void endsWithWrapsInArrayjoin() {
      String r = f.endsWith("BioAg", false, true);
      assertTrue(r.contains("ARRAYJOIN({fldClient}"), "missing ARRAYJOIN: " + r);
      assertTrue(r.contains("LEN("), "missing LEN: " + r);
    }

    @Test
    void eqDoesNotWrapInArrayjoin() {
      // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
      String r = f.eq("Groundwork Bio Ag");
      assertFalse(r.contains("ARRAYJOIN"), "should not wrap eq: " + r);
      assertTrue(r.contains("{fldClient}"), "missing field: " + r);
    }

    @Test
    void notEmptyDoesNotWrap() {
      assertFalse(f.notEmpty().contains("ARRAYJOIN"));
    }

    @Test
    void textFieldUnaffectedRegression() {
      // Regression: FormulaTextField must still emit a bare {field} reference.
      FormulaTextField t = new FormulaTextField("fldName");
      assertFalse(t.contains("hello", false, true).contains("ARRAYJOIN"));
    }
  }

  // endregion

  // region Date field-to-field comparisons

  @Nested
  class DateFieldOperand {
    private final FormulaDateField f = new FormulaDateField("fld123");
    private final FormulaDateField other = new FormulaDateField("fldOther");

    @Test
    void onAnotherField() {
      assertEquals("DATETIME_PARSE({fldOther})=DATETIME_PARSE({fld123})", f.on(other));
    }

    @Test
    void afterAnotherField() {
      assertTrue(f.after(other).contains("DATETIME_PARSE({fldOther})<DATETIME_PARSE({fld123})"));
    }

    @Test
    void betweenMixedOperands() {
      String r = f.between("2025-01-01", other);
      assertTrue(r.startsWith("AND("));
      assertTrue(r.contains("DATETIME_PARSE('2025-01-01')"));
      assertTrue(r.contains("DATETIME_PARSE({fldOther})"));
    }

    @Test
    void stringLiteralStillWorks() {
      String r = f.on("2025-01-15");
      assertTrue(r.contains("DATETIME_PARSE('2025-01-15')"));
      assertTrue(r.contains("=DATETIME_PARSE({fld123})"));
    }
  }

  // endregion

  /**
   * myairtable-53ip — formula-string injection hardening. A value may not break out of its quoted
   * context regardless of embedded quotes/backslashes.
   */
  @Nested
  class Escaping {
    private final FormulaTextField text = new FormulaTextField("fldT");
    private final FormulaId id = new FormulaId();

    @Test
    void quoteInValueStaysInsideTheString() {
      assertEquals("{fldT}=\"a \\\"quoted\\\" b\"", text.eq("a \"quoted\" b"));
    }

    @Test
    void trailingBackslashCannotEscapeTheClosingQuote() {
      // Pre-fix: ...="x\" left the quote live and leaked formula code.
      assertEquals("{fldT}=\"x\\\\\"", text.eq("x\\"));
    }

    @Test
    void backslashThenQuotePayloadIsNeutralized() {
      String evil = "x\\\", TRUE(), \"";
      String formula = text.eq(evil);
      // Every backslash doubled, every quote escaped — the payload cannot
      // terminate the string literal.
      String expected = "{fldT}=\"" + Formulas.escapeFormulaString(evil) + "\"";
      assertEquals(expected, formula);
      assertEquals("x\\\\\\\", TRUE(), \\\"", Formulas.escapeFormulaString(evil));
    }

    @Test
    void recordIdSingleQuoteIsEscaped() {
      assertEquals("RECORD_ID()='rec\\' OR TRUE() OR \\''", id.eq("rec' OR TRUE() OR '"));
    }

    @Test
    void regexBackslashSurvivesRoundTrip() {
      // \d in the pattern -> \\d in formula source; Airtable's string parser
      // unescapes it back to \d for the regex engine.
      assertEquals("REGEX_MATCH({fldT},\"\\\\d+\")", text.regexMatch("\\d+"));
    }

    @Test
    void phoneEqualsEscapesResidualQuotes() {
      String formula = text.phoneEquals("555\"1234");
      assertTrue(formula.endsWith("=\"555\\\"1234\""), formula);
    }
  }
}
