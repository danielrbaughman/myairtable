using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS7.4 — Unit tests for the formula builder DSL. Mirrors the Java/Kotlin/Swift/Rust TestFormula
/// suites (~98 cases). Naming deviation per csharp-plan-v2 §2.3.2: <c>Eq</c>/<c>Neq</c> instead of
/// <c>Equals</c>/<c>NotEquals</c>.
/// </summary>
public class TestFormula
{
    // ---- Combinators ----

    [Fact]
    public void AndCombines() => Assert.Equal("AND(A,B,C)", Formulas.And("A", "B", "C"));

    [Fact]
    public void AndSingleReturnsBare() => Assert.Equal("A", Formulas.And("A"));

    [Fact]
    public void AndEmptyReturnsEmpty() => Assert.Equal("", Formulas.And());

    [Fact]
    public void AndFiltersEmptyStrings() => Assert.Equal("AND(A,B)", Formulas.And("A", "", "B"));

    [Fact]
    public void OrCombines() => Assert.Equal("OR(A,B)", Formulas.Or("A", "B"));

    [Fact]
    public void NotWraps() => Assert.Equal("NOT(A)", Formulas.Not("A"));

    [Fact]
    public void XorCombines() => Assert.Equal("XOR(A,B)", Formulas.Xor("A", "B"));

    [Fact]
    public void XorSingleReturnsBare() => Assert.Equal("X", Formulas.Xor("X"));

    // ---- Record ID ----

    [Fact]
    public void IdEq() => Assert.Equal("RECORD_ID()='rec123'", new FormulaId().Eq("rec123"));

    [Fact]
    public void IdInListEmpty() =>
        Assert.Equal("FALSE()", new FormulaId().InList(new List<string>()));

    [Fact]
    public void IdInListSingle() =>
        Assert.Equal("RECORD_ID()='rec123'", new FormulaId().InList(new List<string> { "rec123" }));

    [Fact]
    public void IdInListMultiple()
    {
        var r = new FormulaId().InList(new List<string> { "rec1", "rec2" });
        Assert.StartsWith("OR(", r);
        Assert.Contains("rec1", r);
        Assert.Contains("rec2", r);
    }

    // ---- Text Field ----

    private static FormulaTextField Text() => new("fld123");

    [Fact]
    public void EqCaseSensitive() => Assert.Equal("{fld123}=\"hello\"", Text().Eq("hello"));

    [Fact]
    public void EqEscapesQuotes() =>
        Assert.Equal("{fld123}=\"say \\\"hi\\\"\"", Text().Eq("say \"hi\""));

    [Fact]
    public void EqCaseInsensitive() => Assert.Contains("LOWER(", Text().Eq("hello", false));

    [Fact]
    public void EqWithTrim() => Assert.Contains("TRIM(", Text().Eq("hello", true, true));

    [Fact]
    public void EqualsAnyCombinesWithOr() =>
        Assert.StartsWith("OR(", Text().EqualsAny(new List<string> { "a", "b" }));

    [Fact]
    public void Neq() => Assert.Equal("{fld123}!=\"x\"", Text().Neq("x"));

    [Fact]
    public void ContainsSubstring() =>
        Assert.Equal("FIND(\"ell\",{fld123})>0", Text().Contains("ell"));

    [Fact]
    public void ContainsCaseInsensitive() =>
        Assert.Contains("LOWER(", Text().Contains("ell", false));

    [Fact]
    public void ContainsAnyCombinesWithOr() =>
        Assert.StartsWith("OR(", Text().ContainsAny(new List<string> { "a", "b" }));

    [Fact]
    public void ContainsAllCombinesWithAnd() =>
        Assert.StartsWith("AND(", Text().ContainsAll(new List<string> { "a", "b" }));

    [Fact]
    public void NotContainsWrapsInNot()
    {
        var r = Text().NotContains("x");
        Assert.StartsWith("NOT(", r);
        Assert.Contains("FIND(", r);
    }

    [Fact]
    public void StartsWithFind1() =>
        Assert.Equal("FIND(\"hel\",{fld123})=1", Text().StartsWith("hel"));

    [Fact]
    public void NotStartsWithFindNot1() =>
        Assert.Equal("FIND(\"hel\",{fld123})!=1", Text().NotStartsWith("hel"));

    [Fact]
    public void EndsWithFormula()
    {
        var r = Text().EndsWith("lo");
        Assert.Contains("FIND(", r);
        Assert.Contains("LEN(", r);
    }

    [Fact]
    public void NotEndsWithFormula()
    {
        var r = Text().NotEndsWith("lo");
        Assert.Contains("FIND(", r);
        Assert.Contains("!=LEN(", r);
    }

    [Fact]
    public void PhoneEqualsNormalized()
    {
        var r = Text().PhoneEquals("+1 (555) 123-4567");
        Assert.Contains("15551234567", r);
        Assert.Contains("SUBSTITUTE", r);
    }

    [Fact]
    public void RegexMatch() =>
        Assert.Equal("REGEX_MATCH({fld123},\"^[A-Z]+$\")", Text().RegexMatch("^[A-Z]+$"));

    [Fact]
    public void EmptyCheck() => Assert.Equal("{fld123}=BLANK()", Text().Empty());

    [Fact]
    public void NotEmptyCheck() => Assert.Equal("{fld123}!=BLANK()", Text().NotEmpty());

    [Fact]
    public void EqCaseInsensitiveAndTrim()
    {
        var r = Text().Eq("hello", false, true);
        Assert.Contains("LOWER(", r);
        Assert.Contains("TRIM(", r);
    }

    [Fact]
    public void ContainsWithTrim() => Assert.Contains("TRIM(", Text().Contains("ell", true, true));

    [Fact]
    public void NeqWithOptions()
    {
        var r = Text().Neq("x", false);
        Assert.Contains("LOWER(", r);
        Assert.Contains("!=", r);
    }

    // ---- Single Select ----

    [Fact]
    public void SelectEq() =>
        Assert.Equal("{fldSS}=\"Choice 1\"", new FormulaSingleSelectField("fldSS").Eq("Choice 1"));

    [Fact]
    public void SelectEqualsAny() =>
        Assert.StartsWith(
            "OR(",
            new FormulaSingleSelectField("fldSS").EqualsAny(new List<string> { "A", "B" })
        );

    [Fact]
    public void SelectNeq() =>
        Assert.Equal("{fldSS}!=\"C\"", new FormulaSingleSelectField("fldSS").Neq("C"));

    [Fact]
    public void SelectEmpty() =>
        Assert.Equal("{fldSS}=BLANK()", new FormulaSingleSelectField("fldSS").Empty());

    // ---- Multi Select ----

    private static FormulaMultiSelectField Multi() => new("fldMS");

    [Fact]
    public void MultiContains() => Assert.Equal("FIND(\"opt\",{fldMS})>0", Multi().Contains("opt"));

    [Fact]
    public void MultiContainsAny() =>
        Assert.StartsWith("OR(", Multi().ContainsAny(new List<string> { "a", "b" }));

    [Fact]
    public void MultiContainsAll() =>
        Assert.StartsWith("AND(", Multi().ContainsAll(new List<string> { "a", "b" }));

    [Fact]
    public void MultiNotContains() => Assert.StartsWith("NOT(", Multi().NotContains("x"));

    // ---- Number Field ----

    private static FormulaNumberField Num() => new("fldN");

    [Fact]
    public void NumEq() => Assert.Equal("{fldN}=42", Num().Eq(42));

    [Fact]
    public void NumNeq() => Assert.Equal("{fldN}!=0", Num().Neq(0));

    [Fact]
    public void NumGreaterThan() => Assert.Equal("{fldN}>10", Num().GreaterThan(10));

    [Fact]
    public void NumLessThan() => Assert.Equal("{fldN}<5", Num().LessThan(5));

    [Fact]
    public void NumGte() => Assert.Equal("{fldN}>=1", Num().GreaterThanOrEquals(1));

    [Fact]
    public void NumLte() => Assert.Equal("{fldN}<=99", Num().LessThanOrEquals(99));

    [Fact]
    public void NumBetweenInclusive()
    {
        var r = Num().Between(1, 10, true);
        Assert.StartsWith("AND(", r);
        Assert.Contains(">=", r);
        Assert.Contains("<=", r);
    }

    [Fact]
    public void NumBetweenExclusive()
    {
        var r = Num().Between(1, 10, false);
        Assert.Contains(">1", r);
        Assert.Contains("<10", r);
    }

    [Fact]
    public void NumEqFloat() => Assert.Equal("{fldN}=3.14", Num().Eq(3.14));

    [Fact]
    public void NumEmpty() => Assert.Equal("{fldN}=BLANK()", Num().Empty());

    // ---- Boolean Field ----

    private static FormulaBooleanField Boolean() => new("fldB");

    [Fact]
    public void BoolIsTrue() => Assert.Equal("{fldB}=TRUE()", Boolean().IsTrue());

    [Fact]
    public void BoolIsFalse() => Assert.Equal("{fldB}=FALSE()", Boolean().IsFalse());

    [Fact]
    public void BoolEqTrue() => Assert.Equal("{fldB}=TRUE()", Boolean().Eq(true));

    [Fact]
    public void BoolEqFalse() => Assert.Equal("{fldB}=FALSE()", Boolean().Eq(false));

    // ---- Date Field ----

    private static FormulaDateField Date() => new("fldD");

    [Fact]
    public void OnDate() =>
        Assert.Equal(
            "DATETIME_PARSE('2025-01-15')=DATETIME_PARSE({fldD})",
            Date().On("2025-01-15")
        );

    [Fact]
    public void NotOnDate() => Assert.Contains("!=", Date().NotOn("2025-01-15"));

    [Fact]
    public void AfterDate() => Assert.Contains("<", Date().After("2025-01-15"));

    [Fact]
    public void BeforeDate() => Assert.Contains(">", Date().Before("2025-01-15"));

    [Fact]
    public void OnOrAfterDate() => Assert.Contains("<=", Date().OnOrAfter("2025-01-15"));

    [Fact]
    public void OnOrBeforeDate() => Assert.Contains(">=", Date().OnOrBefore("2025-01-15"));

    [Fact]
    public void BetweenDatesInclusive() =>
        Assert.StartsWith("AND(", Date().Between("2025-01-01", "2025-12-31", true));

    [Fact]
    public void BetweenDatesExclusive() =>
        Assert.StartsWith("AND(", Date().Between("2025-01-01", "2025-12-31", false));

    [Fact]
    public void DateEmpty() => Assert.Equal("{fldD}=BLANK()", Date().Empty());

    [Fact]
    public void DateNotEmpty() => Assert.Equal("{fldD}!=BLANK()", Date().NotEmpty());

    [Fact]
    public void DaysAgo()
    {
        var r = Date().After().DaysAgo(7);
        Assert.Contains("DATETIME_DIFF(NOW()", r);
        Assert.Contains("\"days\"", r);
        Assert.Contains("<7", r);
    }

    [Fact]
    public void YearsAgo() => Assert.Contains("\"years\"", Date().Before().YearsAgo(1));

    [Fact]
    public void WeeksAgo()
    {
        var r = Date().On().WeeksAgo(2);
        Assert.Contains("\"weeks\"", r);
        Assert.Contains("=2", r);
    }

    [Fact]
    public void HoursAgo() => Assert.Contains("\"hours\"", Date().After().HoursAgo(24));

    [Fact]
    public void MinutesAgo() => Assert.Contains("\"minutes\"", Date().After().MinutesAgo(30));

    [Fact]
    public void SecondsAgo() => Assert.Contains("\"seconds\"", Date().After().SecondsAgo(60));

    [Fact]
    public void MonthsAgo() => Assert.Contains("\"months\"", Date().Before().MonthsAgo(3));

    [Fact]
    public void QuartersAgo() => Assert.Contains("\"quarters\"", Date().Before().QuartersAgo(2));

    [Fact]
    public void MillisecondsAgo() =>
        Assert.Contains("\"milliseconds\"", Date().After().MillisecondsAgo(500));

    [Fact]
    public void OnOrAfterChainDays() => Assert.Contains("<=", Date().OnOrAfter().DaysAgo(30));

    [Fact]
    public void OnOrBeforeChainDays() => Assert.Contains(">=", Date().OnOrBefore().DaysAgo(30));

    [Fact]
    public void NotOnChainDays() => Assert.Contains("!=", Date().NotOn().DaysAgo(1));

    [Fact]
    public void OnChainYears() => Assert.Contains("=5", Date().On().YearsAgo(5));

    // ---- Attachment Field ----

    private static FormulaAttachmentsField Attach() => new("fldA");

    [Fact]
    public void AttachmentEmpty() => Assert.Equal("LEN({fldA})=0", Attach().Empty());

    [Fact]
    public void AttachmentNotEmpty() => Assert.Equal("LEN({fldA})>0", Attach().NotEmpty());

    [Fact]
    public void AttachmentCount() => Assert.Equal("LEN({fldA})=3", Attach().Count(3));

    // ---- Lookup Field ----

    private static FormulaLookupField Lookup() => new("fldClient");

    [Fact]
    public void LookupContainsWrapsInArrayjoin()
    {
        var r = Lookup().Contains("groundwork", false, true);
        Assert.Contains("ARRAYJOIN({fldClient}", r);
        Assert.Contains("FIND(", r);
        Assert.Contains("LOWER(", r);
    }

    [Fact]
    public void LookupStartsWithWrapsInArrayjoin() =>
        Assert.Contains("ARRAYJOIN({fldClient}", Lookup().StartsWith("Ground", false, true));

    [Fact]
    public void LookupEndsWithWrapsInArrayjoin()
    {
        var r = Lookup().EndsWith("BioAg", false, true);
        Assert.Contains("ARRAYJOIN({fldClient}", r);
        Assert.Contains("LEN(", r);
    }

    [Fact]
    public void LookupEqDoesNotWrapInArrayjoin()
    {
        // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
        var r = Lookup().Eq("Groundwork Bio Ag");
        Assert.DoesNotContain("ARRAYJOIN", r);
        Assert.Contains("{fldClient}", r);
    }

    [Fact]
    public void LookupNotEmptyDoesNotWrap() =>
        Assert.DoesNotContain("ARRAYJOIN", Lookup().NotEmpty());

    [Fact]
    public void TextFieldUnaffectedRegression() =>
        Assert.DoesNotContain(
            "ARRAYJOIN",
            new FormulaTextField("fldName").Contains("hello", false, true)
        );

    // ---- Date field-to-field comparisons ----

    [Fact]
    public void OnAnotherField() =>
        Assert.Equal(
            "DATETIME_PARSE({fldOther})=DATETIME_PARSE({fld123})",
            new FormulaDateField("fld123").On(new FormulaDateField("fldOther"))
        );

    [Fact]
    public void AfterAnotherField() =>
        Assert.Contains(
            "DATETIME_PARSE({fldOther})<DATETIME_PARSE({fld123})",
            new FormulaDateField("fld123").After(new FormulaDateField("fldOther"))
        );

    [Fact]
    public void BetweenMixedOperands()
    {
        var r = new FormulaDateField("fld123").Between(
            "2025-01-01",
            new FormulaDateField("fldOther")
        );
        Assert.StartsWith("AND(", r);
        Assert.Contains("DATETIME_PARSE('2025-01-01')", r);
        Assert.Contains("DATETIME_PARSE({fldOther})", r);
    }

    [Fact]
    public void StringLiteralStillWorks()
    {
        var r = new FormulaDateField("fld123").On("2025-01-15");
        Assert.Contains("DATETIME_PARSE('2025-01-15')", r);
        Assert.Contains("=DATETIME_PARSE({fld123})", r);
    }

    // ---- Escaping / injection hardening ----

    [Fact]
    public void QuoteInValueStaysInsideTheString() =>
        Assert.Equal(
            "{fldT}=\"a \\\"quoted\\\" b\"",
            new FormulaTextField("fldT").Eq("a \"quoted\" b")
        );

    [Fact]
    public void TrailingBackslashCannotEscapeTheClosingQuote() =>
        // Pre-fix: ...="x\" left the quote live and leaked formula code.
        Assert.Equal("{fldT}=\"x\\\\\"", new FormulaTextField("fldT").Eq("x\\"));

    [Fact]
    public void BackslashThenQuotePayloadIsNeutralized()
    {
        var evil = "x\\\", TRUE(), \"";
        var formula = new FormulaTextField("fldT").Eq(evil);
        var expected = "{fldT}=\"" + Formulas.EscapeFormulaString(evil) + "\"";
        Assert.Equal(expected, formula);
    }

    [Fact]
    public void RecordIdSingleQuoteIsEscaped() =>
        Assert.Equal(
            "RECORD_ID()='rec\\' OR TRUE() OR \\''",
            new FormulaId().Eq("rec' OR TRUE() OR '")
        );

    [Fact]
    public void RegexBackslashSurvivesRoundTrip() =>
        // \d -> \\d in formula source; Airtable's string parser unescapes back to \d.
        Assert.Equal(
            "REGEX_MATCH({fldT},\"\\\\d+\")",
            new FormulaTextField("fldT").RegexMatch("\\d+")
        );

    [Fact]
    public void PhoneEqualsEscapesResidualQuotes()
    {
        var formula = new FormulaTextField("fldT").PhoneEquals("555\"1234");
        Assert.EndsWith("=\"555\\\"1234\"", formula);
    }
}
