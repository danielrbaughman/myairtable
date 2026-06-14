package airtable

// Offline parity tests for the formula DSL. Ports tests/test_formula.rs
// category-by-category, asserting the emitted filterByFormula strings. The Go
// builders reference field NAMES ({Field}) rather than field IDs.

import (
	"strings"
	"testing"
)

func assertEq(t *testing.T, got, want string) {
	t.Helper()
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func assertContains(t *testing.T, got, sub string) {
	t.Helper()
	if !strings.Contains(got, sub) {
		t.Fatalf("%q does not contain %q", got, sub)
	}
}

func assertNotContains(t *testing.T, got, sub string) {
	t.Helper()
	if strings.Contains(got, sub) {
		t.Fatalf("%q should not contain %q", got, sub)
	}
}

func assertPrefix(t *testing.T, got, prefix string) {
	t.Helper()
	if !strings.HasPrefix(got, prefix) {
		t.Fatalf("%q does not start with %q", got, prefix)
	}
}

// =============================================================================
// Combinators
// =============================================================================

func TestAndCombinesFormulas(t *testing.T) {
	assertEq(t, And(NewFormula("A"), NewFormula("B"), NewFormula("C")).String(), "AND(A,B,C)")
}

func TestAndSingleReturnsBare(t *testing.T) {
	assertEq(t, And(NewFormula("A")).String(), "A")
}

func TestAndEmptyReturnsEmpty(t *testing.T) {
	assertEq(t, And().String(), "")
}

func TestAndFiltersEmptyStrings(t *testing.T) {
	assertEq(t, And(NewFormula("A"), NewFormula(""), NewFormula("B")).String(), "AND(A,B)")
}

func TestOrCombinesFormulas(t *testing.T) {
	assertEq(t, Or(NewFormula("A"), NewFormula("B")).String(), "OR(A,B)")
}

func TestOrSingleReturnsBare(t *testing.T) {
	assertEq(t, Or(NewFormula("A")).String(), "A")
}

func TestNotWrapsFormula(t *testing.T) {
	assertEq(t, Not(NewFormula("A")).String(), "NOT(A)")
}

func TestXorCombinesFormulas(t *testing.T) {
	assertEq(t, Xor(NewFormula("A"), NewFormula("B")).String(), "XOR(A,B)")
}

func TestXorFiltersEmptyStrings(t *testing.T) {
	assertEq(t, Xor(NewFormula("A"), NewFormula(""), NewFormula("B")).String(), "XOR(A,B)")
}

// =============================================================================
// Record ID
// =============================================================================

func TestIDEquals(t *testing.T) {
	assertEq(t, NewIDField().Eq("rec123").String(), "RECORD_ID()='rec123'")
}

func TestIDInListEmpty(t *testing.T) {
	assertEq(t, NewIDField().InList(nil).String(), "FALSE()")
}

func TestIDInListSingle(t *testing.T) {
	assertEq(t, NewIDField().InList([]string{"rec123"}).String(), "RECORD_ID()='rec123'")
}

func TestIDInListMultiple(t *testing.T) {
	got := NewIDField().InList([]string{"rec1", "rec2"}).String()
	assertPrefix(t, got, "OR(")
	assertContains(t, got, "rec1")
	assertContains(t, got, "rec2")
}

func TestIDEscapesSingleQuote(t *testing.T) {
	assertEq(t, NewIDField().Eq("rec'x").String(), "RECORD_ID()='rec\\'x'")
}

// =============================================================================
// Text Field — equality
// =============================================================================

func TestTextEqualsCaseSensitive(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.Eq("hello", true, false).String(), `{Field}="hello"`)
}

func TestTextEqualsEscapesQuotes(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.Eq(`say "hi"`, true, false).String(), `{Field}="say \"hi\""`)
}

func TestTextEqualsCaseInsensitive(t *testing.T) {
	f := NewTextField("Field")
	assertContains(t, f.Eq("hello", false, false).String(), "LOWER(")
}

func TestTextEqualsWithTrim(t *testing.T) {
	f := NewTextField("Field")
	assertContains(t, f.Eq("hello", true, true).String(), "TRIM(")
}

func TestTextEqualsAny(t *testing.T) {
	f := NewTextField("Field")
	got := f.EqualsAny([]string{"a", "b"}, true, false).String()
	assertPrefix(t, got, "OR(")
	assertContains(t, got, `{Field}="a"`)
	assertContains(t, got, `{Field}="b"`)
}

func TestTextNotEquals(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.Neq("hello", true, false).String(), `{Field}!="hello"`)
}

// =============================================================================
// Text Field — substring search
// =============================================================================

func TestTextContainsCaseInsensitiveTrimmed(t *testing.T) {
	f := NewTextField("Field")
	got := f.Contains("test", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, "LOWER(")
	assertContains(t, got, "TRIM(")
	assertContains(t, got, ">0")
}

func TestTextContainsCaseSensitive(t *testing.T) {
	f := NewTextField("Field")
	got := f.Contains("test", true, false).String()
	assertNotContains(t, got, "LOWER(")
	assertContains(t, got, "FIND(")
}

func TestTextContainsAny(t *testing.T) {
	f := NewTextField("Field")
	assertPrefix(t, f.ContainsAny([]string{"a", "b"}, false, true).String(), "OR(")
}

func TestTextContainsAll(t *testing.T) {
	f := NewTextField("Field")
	assertPrefix(t, f.ContainsAll([]string{"a", "b"}, false, true).String(), "AND(")
}

func TestTextNotContains(t *testing.T) {
	f := NewTextField("Field")
	assertPrefix(t, f.NotContains("test", false, true).String(), "NOT(")
}

// =============================================================================
// Text Field — starts/ends with
// =============================================================================

func TestTextStartsWith(t *testing.T) {
	f := NewTextField("Field")
	got := f.StartsWith("hello", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, ")=1")
}

func TestTextNotStartsWith(t *testing.T) {
	f := NewTextField("Field")
	got := f.NotStartsWith("hello", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, ")!=1")
}

func TestTextEndsWith(t *testing.T) {
	f := NewTextField("Field")
	got := f.EndsWith("world", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, "LEN(")
	assertContains(t, got, "+1")
}

func TestTextNotEndsWith(t *testing.T) {
	f := NewTextField("Field")
	got := f.NotEndsWith("world", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, "!=LEN(")
}

// =============================================================================
// Text Field — special
// =============================================================================

func TestTextPhoneEquals(t *testing.T) {
	f := NewTextField("Field")
	got := f.PhoneEquals("+1 (555) 123-4567").String()
	assertContains(t, got, "SUBSTITUTE(")
	assertContains(t, got, "15551234567")
}

func TestTextRegexMatch(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.RegexMatch("^[A-Z]+$").String(), `REGEX_MATCH({Field},"^[A-Z]+$")`)
}

func TestTextEmpty(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.IsEmpty().String(), "{Field}=BLANK()")
}

func TestTextNotEmpty(t *testing.T) {
	f := NewTextField("Field")
	assertEq(t, f.IsNotEmpty().String(), "{Field}!=BLANK()")
}

// =============================================================================
// Single Select Field
// =============================================================================

func TestSingleSelectEquals(t *testing.T) {
	f := NewSingleSelectField("Field")
	assertEq(t, f.Eq("Choice 1", true, false).String(), `{Field}="Choice 1"`)
}

func TestSingleSelectEqualsAny(t *testing.T) {
	f := NewSingleSelectField("Field")
	assertPrefix(t, f.EqualsAny([]string{"A", "B"}, true, false).String(), "OR(")
}

func TestSingleSelectNotEquals(t *testing.T) {
	f := NewSingleSelectField("Field")
	assertContains(t, f.Neq("Choice 1", true, false).String(), `!="Choice 1"`)
}

func TestSingleSelectEmpty(t *testing.T) {
	f := NewSingleSelectField("Field")
	assertEq(t, f.IsEmpty().String(), "{Field}=BLANK()")
}

// =============================================================================
// Multi Select Field
// =============================================================================

func TestMultiSelectContainsOption(t *testing.T) {
	f := NewMultiSelectField("Field")
	got := f.Contains("Option 1", false, true).String()
	assertContains(t, got, "FIND(")
	assertContains(t, got, ">0")
}

func TestMultiSelectContainsAnyOptions(t *testing.T) {
	f := NewMultiSelectField("Field")
	assertPrefix(t, f.ContainsAny([]string{"A", "B"}, false, true).String(), "OR(")
}

func TestMultiSelectContainsAllOptions(t *testing.T) {
	f := NewMultiSelectField("Field")
	assertPrefix(t, f.ContainsAll([]string{"A", "B"}, false, true).String(), "AND(")
}

func TestMultiSelectNotContainsOption(t *testing.T) {
	f := NewMultiSelectField("Field")
	assertPrefix(t, f.NotContains("A", false, true).String(), "NOT(")
}

// =============================================================================
// Number Field
// =============================================================================

func TestNumberEquals(t *testing.T) {
	assertEq(t, NewNumberField("Field").Eq(42).String(), "{Field}=42")
}

func TestNumberNotEquals(t *testing.T) {
	assertEq(t, NewNumberField("Field").Neq(42).String(), "{Field}!=42")
}

func TestNumberGreaterThan(t *testing.T) {
	assertEq(t, NewNumberField("Field").GreaterThan(10).String(), "{Field}>10")
}

func TestNumberLessThan(t *testing.T) {
	assertEq(t, NewNumberField("Field").LessThan(10).String(), "{Field}<10")
}

func TestNumberGreaterThanOrEqual(t *testing.T) {
	assertEq(t, NewNumberField("Field").GreaterThanOrEqual(10).String(), "{Field}>=10")
}

func TestNumberLessThanOrEqual(t *testing.T) {
	assertEq(t, NewNumberField("Field").LessThanOrEqual(10).String(), "{Field}<=10")
}

func TestNumberBetweenInclusive(t *testing.T) {
	assertEq(t, NewNumberField("Field").Between(10, 20, true).String(), "AND({Field}>=10,{Field}<=20)")
}

func TestNumberBetweenExclusive(t *testing.T) {
	assertEq(t, NewNumberField("Field").Between(10, 20, false).String(), "AND({Field}>10,{Field}<20)")
}

func TestNumberWithFloat(t *testing.T) {
	assertEq(t, NewNumberField("Field").Eq(3.14).String(), "{Field}=3.14")
}

func TestNumberEmpty(t *testing.T) {
	assertEq(t, NewNumberField("Field").IsEmpty().String(), "{Field}=BLANK()")
}

// =============================================================================
// Boolean Field
// =============================================================================

func TestBooleanIsTrue(t *testing.T) {
	assertEq(t, NewBooleanField("Field").IsTrue().String(), "{Field}=TRUE()")
}

func TestBooleanIsFalse(t *testing.T) {
	assertEq(t, NewBooleanField("Field").IsFalse().String(), "{Field}=FALSE()")
}

func TestBooleanEqualsTrue(t *testing.T) {
	assertEq(t, NewBooleanField("Field").Eq(true).String(), "{Field}=TRUE()")
}

func TestBooleanEqualsFalse(t *testing.T) {
	assertEq(t, NewBooleanField("Field").Eq(false).String(), "{Field}=FALSE()")
}

// =============================================================================
// Date Field — absolute dates
// =============================================================================

func TestDateOn(t *testing.T) {
	got := NewDateField("Field").OnDate("2025-01-15").String()
	assertContains(t, got, "DATETIME_PARSE('2025-01-15')")
	assertContains(t, got, "=DATETIME_PARSE({Field})")
}

func TestDateNotOn(t *testing.T) {
	assertContains(t, NewDateField("Field").NotOnDate("2025-01-15").String(), "!=")
}

func TestDateAfter(t *testing.T) {
	assertContains(t, NewDateField("Field").AfterDate("2025-01-15").String(), "<DATETIME_PARSE")
}

func TestDateBefore(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeDate("2025-01-15").String(), ">DATETIME_PARSE")
}

func TestDateOnOrAfter(t *testing.T) {
	assertContains(t, NewDateField("Field").OnOrAfterDate("2025-01-15").String(), "<=DATETIME_PARSE")
}

func TestDateOnOrBefore(t *testing.T) {
	assertContains(t, NewDateField("Field").OnOrBeforeDate("2025-01-15").String(), ">=DATETIME_PARSE")
}

func TestDateBetweenInclusive(t *testing.T) {
	assertPrefix(t, NewDateField("Field").BetweenDates("2025-01-01", "2025-12-31", true).String(), "AND(")
}

func TestDateBetweenExclusive(t *testing.T) {
	assertPrefix(t, NewDateField("Field").BetweenDates("2025-01-01", "2025-12-31", false).String(), "AND(")
}

func TestDateOnField(t *testing.T) {
	// Field-vs-field comparison.
	got := NewDateField("First").On(NewDateField("Second")).String()
	assertContains(t, got, "DATETIME_PARSE({Second})")
	assertContains(t, got, "DATETIME_PARSE({First})")
}

func TestDateEmpty(t *testing.T) {
	assertEq(t, NewDateField("Field").IsEmpty().String(), "{Field}=BLANK()")
}

func TestDateNotEmpty(t *testing.T) {
	assertEq(t, NewDateField("Field").IsNotEmpty().String(), "{Field}!=BLANK()")
}

// =============================================================================
// Date Field — time-ago chaining
// =============================================================================

func TestDateBeforeDaysAgo(t *testing.T) {
	got := NewDateField("Field").BeforeChain().DaysAgo(7).String()
	assertContains(t, got, `DATETIME_DIFF(NOW(),{Field},"days")`)
	assertContains(t, got, ">7")
}

func TestDateAfterYearsAgo(t *testing.T) {
	got := NewDateField("Field").AfterChain().YearsAgo(1).String()
	assertContains(t, got, `"years"`)
	assertContains(t, got, "<1")
}

func TestDateOnChainDaysAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").OnChain().DaysAgo(30).String(), "=30")
}

func TestDateOnOrAfterChainWeeksAgo(t *testing.T) {
	got := NewDateField("Field").OnOrAfterChain().WeeksAgo(2).String()
	assertContains(t, got, `"weeks"`)
	assertContains(t, got, "<=2")
}

func TestDateHoursAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().HoursAgo(24).String(), `"hours"`)
}

func TestDateMinutesAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().MinutesAgo(60).String(), `"minutes"`)
}

func TestDateSecondsAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().SecondsAgo(3600).String(), `"seconds"`)
}

func TestDateMonthsAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().MonthsAgo(6).String(), `"months"`)
}

func TestDateQuartersAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().QuartersAgo(2).String(), `"quarters"`)
}

func TestDateMillisecondsAgo(t *testing.T) {
	assertContains(t, NewDateField("Field").BeforeChain().MillisecondsAgo(5000).String(), `"milliseconds"`)
}

func TestDateNotOnChain(t *testing.T) {
	assertContains(t, NewDateField("Field").NotOnChain().DaysAgo(1).String(), "!=1")
}

func TestDateOnOrBeforeChain(t *testing.T) {
	assertContains(t, NewDateField("Field").OnOrBeforeChain().DaysAgo(1).String(), ">=1")
}

// =============================================================================
// Attachments Field
// =============================================================================

func TestAttachmentsNotEmpty(t *testing.T) {
	assertEq(t, NewAttachmentsField("Field").IsNotEmpty().String(), "LEN({Field})>0")
}

func TestAttachmentsEmpty(t *testing.T) {
	assertEq(t, NewAttachmentsField("Field").IsEmpty().String(), "LEN({Field})=0")
}

func TestAttachmentsCount(t *testing.T) {
	assertEq(t, NewAttachmentsField("Field").Count(3).String(), "LEN({Field})=3")
}

// =============================================================================
// Lookup Field
// =============================================================================
// LookupField wraps the field reference in ARRAYJOIN for string ops so Airtable
// can coerce the array to a string. Equality (=) is unaffected.

func TestLookupContainsWrapsInArrayjoin(t *testing.T) {
	f := NewLookupField("Client")
	got := f.Contains("groundwork", false, true).String()
	assertContains(t, got, "ARRAYJOIN({Client}")
	assertContains(t, got, "FIND(")
	assertContains(t, got, "LOWER(")
}

func TestLookupStartsWithWrapsInArrayjoin(t *testing.T) {
	f := NewLookupField("Client")
	assertContains(t, f.StartsWith("Ground", false, true).String(), "ARRAYJOIN({Client}")
}

func TestLookupEndsWithWrapsInArrayjoin(t *testing.T) {
	f := NewLookupField("Client")
	got := f.EndsWith("BioAg", false, true).String()
	assertContains(t, got, "ARRAYJOIN({Client}")
	assertContains(t, got, "LEN(")
}

func TestLookupEqualsDoesNotWrapInArrayjoin(t *testing.T) {
	f := NewLookupField("Client")
	got := f.Eq("Groundwork Bio Ag", true, false).String()
	assertNotContains(t, got, "ARRAYJOIN")
	assertContains(t, got, "{Client}")
}

func TestLookupNotEmptyDoesNotWrap(t *testing.T) {
	f := NewLookupField("Client")
	assertNotContains(t, f.IsNotEmpty().String(), "ARRAYJOIN")
}

func TestTextFieldUnaffectedRegression(t *testing.T) {
	// Regression: TextField must still emit a bare {field} reference.
	f := NewTextField("Name")
	assertNotContains(t, f.Contains("hello", false, true).String(), "ARRAYJOIN")
}

// =============================================================================
// Formula helpers
// =============================================================================

func TestFormulaIsEmpty(t *testing.T) {
	if !And().IsEmpty() {
		t.Fatal("empty And should report IsEmpty")
	}
	if NewFormula("A").IsEmpty() {
		t.Fatal("non-empty formula should not report IsEmpty")
	}
}

func TestWithFilterFormula(t *testing.T) {
	q := (&Query{}).WithFilterFormula(NewTextField("Name").Eq("x", true, false))
	assertEq(t, q.Filter, `{Name}="x"`)
}
