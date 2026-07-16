// Formula builder DSL (C# TestFormula parity, 98 cases).
#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_string.hpp>

#include <string>
#include <vector>

#include "formula_attachments_field.hpp"
#include "formula_boolean_field.hpp"
#include "formula_date_field.hpp"
#include "formula_field.hpp"
#include "formula_id.hpp"
#include "formula_lookup_field.hpp"
#include "formula_multi_select_field.hpp"
#include "formula_number_field.hpp"
#include "formula_single_select_field.hpp"
#include "formula_text_field.hpp"
#include "formulas.hpp"

using namespace myairtable;
using Catch::Matchers::ContainsSubstring;
using Catch::Matchers::EndsWith;
using Catch::Matchers::StartsWith;

namespace {
FormulaTextField text() {
    return FormulaTextField("fld123");
}
FormulaMultiSelectField multi() {
    return FormulaMultiSelectField("fldMS");
}
FormulaNumberField num_field() {
    return FormulaNumberField("fldN");
}
FormulaBooleanField bool_field() {
    return FormulaBooleanField("fldB");
}
FormulaDateField date_field() {
    return FormulaDateField("fldD");
}
FormulaAttachmentsField attach() {
    return FormulaAttachmentsField("fldA");
}
FormulaLookupField lookup() {
    return FormulaLookupField("fldClient");
}
} // namespace

// ---- Combinators ----

TEST_CASE("and combines", "[formula]") {
    REQUIRE(Formulas::and_({"A", "B", "C"}) == "AND(A,B,C)");
}

TEST_CASE("and single returns bare", "[formula]") {
    REQUIRE(Formulas::and_({"A"}) == "A");
}

TEST_CASE("and empty returns empty", "[formula]") {
    REQUIRE(Formulas::and_(std::vector<std::string>{}) == "");
}

TEST_CASE("and filters empty strings", "[formula]") {
    REQUIRE(Formulas::and_({"A", "", "B"}) == "AND(A,B)");
}

TEST_CASE("or combines", "[formula]") {
    REQUIRE(Formulas::or_({"A", "B"}) == "OR(A,B)");
}

TEST_CASE("not wraps", "[formula]") {
    REQUIRE(Formulas::not_("A") == "NOT(A)");
}

TEST_CASE("xor combines", "[formula]") {
    REQUIRE(Formulas::xor_({"A", "B"}) == "XOR(A,B)");
}

TEST_CASE("xor single returns bare", "[formula]") {
    REQUIRE(Formulas::xor_({"X"}) == "X");
}

// ---- Record ID ----

TEST_CASE("id eq", "[formula]") {
    REQUIRE(FormulaId().eq("rec123") == "RECORD_ID()='rec123'");
}

TEST_CASE("id in list empty", "[formula]") {
    REQUIRE(FormulaId().in_list(std::vector<std::string>{}) == "FALSE()");
}

TEST_CASE("id in list single", "[formula]") {
    REQUIRE(FormulaId().in_list({"rec123"}) == "RECORD_ID()='rec123'");
}

TEST_CASE("id in list multiple", "[formula]") {
    const std::string r = FormulaId().in_list({"rec1", "rec2"});
    REQUIRE_THAT(r, StartsWith("OR("));
    REQUIRE_THAT(r, ContainsSubstring("rec1"));
    REQUIRE_THAT(r, ContainsSubstring("rec2"));
}

// ---- Text Field ----

TEST_CASE("eq case sensitive", "[formula]") {
    REQUIRE(text().eq("hello") == "{fld123}=\"hello\"");
}

TEST_CASE("eq escapes quotes", "[formula]") {
    REQUIRE(text().eq("say \"hi\"") == "{fld123}=\"say \\\"hi\\\"\"");
}

TEST_CASE("eq case insensitive", "[formula]") {
    REQUIRE_THAT(text().eq("hello", false), ContainsSubstring("LOWER("));
}

TEST_CASE("eq with trim", "[formula]") {
    REQUIRE_THAT(text().eq("hello", true, true), ContainsSubstring("TRIM("));
}

TEST_CASE("equals any combines with or", "[formula]") {
    REQUIRE_THAT(text().equals_any({"a", "b"}), StartsWith("OR("));
}

TEST_CASE("neq", "[formula]") {
    REQUIRE(text().neq("x") == "{fld123}!=\"x\"");
}

TEST_CASE("contains substring", "[formula]") {
    REQUIRE(text().contains("ell") == "FIND(\"ell\",{fld123})>0");
}

TEST_CASE("contains case insensitive", "[formula]") {
    REQUIRE_THAT(text().contains("ell", false), ContainsSubstring("LOWER("));
}

TEST_CASE("contains any combines with or", "[formula]") {
    REQUIRE_THAT(text().contains_any({"a", "b"}), StartsWith("OR("));
}

TEST_CASE("contains all combines with and", "[formula]") {
    REQUIRE_THAT(text().contains_all({"a", "b"}), StartsWith("AND("));
}

TEST_CASE("not contains wraps in not", "[formula]") {
    const std::string r = text().not_contains("x");
    REQUIRE_THAT(r, StartsWith("NOT("));
    REQUIRE_THAT(r, ContainsSubstring("FIND("));
}

TEST_CASE("starts with find 1", "[formula]") {
    REQUIRE(text().starts_with("hel") == "FIND(\"hel\",{fld123})=1");
}

TEST_CASE("not starts with find not 1", "[formula]") {
    REQUIRE(text().not_starts_with("hel") == "FIND(\"hel\",{fld123})!=1");
}

TEST_CASE("ends with formula", "[formula]") {
    const std::string r = text().ends_with("lo");
    REQUIRE_THAT(r, ContainsSubstring("FIND("));
    REQUIRE_THAT(r, ContainsSubstring("LEN("));
}

TEST_CASE("not ends with formula", "[formula]") {
    const std::string r = text().not_ends_with("lo");
    REQUIRE_THAT(r, ContainsSubstring("FIND("));
    REQUIRE_THAT(r, ContainsSubstring("!=LEN("));
}

TEST_CASE("phone equals normalized", "[formula]") {
    const std::string r = text().phone_equals("+1 (555) 123-4567");
    REQUIRE_THAT(r, ContainsSubstring("15551234567"));
    REQUIRE_THAT(r, ContainsSubstring("SUBSTITUTE"));
}

TEST_CASE("regex match", "[formula]") {
    REQUIRE(text().regex_match("^[A-Z]+$") == "REGEX_MATCH({fld123},\"^[A-Z]+$\")");
}

TEST_CASE("empty check", "[formula]") {
    REQUIRE(text().is_empty() == "{fld123}=BLANK()");
}

TEST_CASE("not empty check", "[formula]") {
    REQUIRE(text().is_not_empty() == "{fld123}!=BLANK()");
}

TEST_CASE("eq case insensitive and trim", "[formula]") {
    const std::string r = text().eq("hello", false, true);
    REQUIRE_THAT(r, ContainsSubstring("LOWER("));
    REQUIRE_THAT(r, ContainsSubstring("TRIM("));
}

TEST_CASE("contains with trim", "[formula]") {
    REQUIRE_THAT(text().contains("ell", true, true), ContainsSubstring("TRIM("));
}

TEST_CASE("neq with options", "[formula]") {
    const std::string r = text().neq("x", false);
    REQUIRE_THAT(r, ContainsSubstring("LOWER("));
    REQUIRE_THAT(r, ContainsSubstring("!="));
}

// ---- Single Select ----

TEST_CASE("select eq", "[formula]") {
    REQUIRE(FormulaSingleSelectField("fldSS").eq("Choice 1") == "{fldSS}=\"Choice 1\"");
}

TEST_CASE("select equals any", "[formula]") {
    REQUIRE_THAT(FormulaSingleSelectField("fldSS").equals_any({"A", "B"}), StartsWith("OR("));
}

TEST_CASE("select neq", "[formula]") {
    REQUIRE(FormulaSingleSelectField("fldSS").neq("C") == "{fldSS}!=\"C\"");
}

TEST_CASE("select empty", "[formula]") {
    REQUIRE(FormulaSingleSelectField("fldSS").is_empty() == "{fldSS}=BLANK()");
}

// ---- Multi Select ----

TEST_CASE("multi contains", "[formula]") {
    REQUIRE(multi().contains("opt") == "FIND(\"opt\",{fldMS})>0");
}

TEST_CASE("multi contains any", "[formula]") {
    REQUIRE_THAT(multi().contains_any({"a", "b"}), StartsWith("OR("));
}

TEST_CASE("multi contains all", "[formula]") {
    REQUIRE_THAT(multi().contains_all({"a", "b"}), StartsWith("AND("));
}

TEST_CASE("multi not contains", "[formula]") {
    REQUIRE_THAT(multi().not_contains("x"), StartsWith("NOT("));
}

// ---- Number Field ----

TEST_CASE("num eq", "[formula]") {
    REQUIRE(num_field().eq(42) == "{fldN}=42");
}

TEST_CASE("num neq", "[formula]") {
    REQUIRE(num_field().neq(0) == "{fldN}!=0");
}

TEST_CASE("num greater than", "[formula]") {
    REQUIRE(num_field().greater_than(10) == "{fldN}>10");
}

TEST_CASE("num less than", "[formula]") {
    REQUIRE(num_field().less_than(5) == "{fldN}<5");
}

TEST_CASE("num gte", "[formula]") {
    REQUIRE(num_field().greater_than_or_equals(1) == "{fldN}>=1");
}

TEST_CASE("num lte", "[formula]") {
    REQUIRE(num_field().less_than_or_equals(99) == "{fldN}<=99");
}

TEST_CASE("num between inclusive", "[formula]") {
    const std::string r = num_field().between(1, 10, true);
    REQUIRE_THAT(r, StartsWith("AND("));
    REQUIRE_THAT(r, ContainsSubstring(">="));
    REQUIRE_THAT(r, ContainsSubstring("<="));
}

TEST_CASE("num between exclusive", "[formula]") {
    const std::string r = num_field().between(1, 10, false);
    REQUIRE_THAT(r, ContainsSubstring(">1"));
    REQUIRE_THAT(r, ContainsSubstring("<10"));
}

TEST_CASE("num eq float", "[formula]") {
    REQUIRE(num_field().eq(3.14) == "{fldN}=3.14");
}

TEST_CASE("num empty", "[formula]") {
    REQUIRE(num_field().is_empty() == "{fldN}=BLANK()");
}

// ---- Boolean Field ----

TEST_CASE("bool is true", "[formula]") {
    REQUIRE(bool_field().is_true() == "{fldB}=TRUE()");
}

TEST_CASE("bool is false", "[formula]") {
    REQUIRE(bool_field().is_false() == "{fldB}=FALSE()");
}

TEST_CASE("bool eq true", "[formula]") {
    REQUIRE(bool_field().eq(true) == "{fldB}=TRUE()");
}

TEST_CASE("bool eq false", "[formula]") {
    REQUIRE(bool_field().eq(false) == "{fldB}=FALSE()");
}

// ---- Date Field ----

TEST_CASE("on date", "[formula]") {
    REQUIRE(date_field().on("2025-01-15") == "DATETIME_PARSE('2025-01-15')=DATETIME_PARSE({fldD})");
}

TEST_CASE("not on date", "[formula]") {
    REQUIRE_THAT(date_field().not_on("2025-01-15"), ContainsSubstring("!="));
}

TEST_CASE("after date", "[formula]") {
    REQUIRE_THAT(date_field().after("2025-01-15"), ContainsSubstring("<"));
}

TEST_CASE("before date", "[formula]") {
    REQUIRE_THAT(date_field().before("2025-01-15"), ContainsSubstring(">"));
}

TEST_CASE("on or after date", "[formula]") {
    REQUIRE_THAT(date_field().on_or_after("2025-01-15"), ContainsSubstring("<="));
}

TEST_CASE("on or before date", "[formula]") {
    REQUIRE_THAT(date_field().on_or_before("2025-01-15"), ContainsSubstring(">="));
}

TEST_CASE("between dates inclusive", "[formula]") {
    REQUIRE_THAT(date_field().between("2025-01-01", "2025-12-31", true), StartsWith("AND("));
}

TEST_CASE("between dates exclusive", "[formula]") {
    REQUIRE_THAT(date_field().between("2025-01-01", "2025-12-31", false), StartsWith("AND("));
}

TEST_CASE("date empty", "[formula]") {
    REQUIRE(date_field().is_empty() == "{fldD}=BLANK()");
}

TEST_CASE("date not empty", "[formula]") {
    REQUIRE(date_field().is_not_empty() == "{fldD}!=BLANK()");
}

TEST_CASE("days ago", "[formula]") {
    const std::string r = date_field().after().days_ago(7);
    REQUIRE_THAT(r, ContainsSubstring("DATETIME_DIFF(NOW()"));
    REQUIRE_THAT(r, ContainsSubstring("\"days\""));
    REQUIRE_THAT(r, ContainsSubstring("<7"));
}

TEST_CASE("years ago", "[formula]") {
    REQUIRE_THAT(date_field().before().years_ago(1), ContainsSubstring("\"years\""));
}

TEST_CASE("weeks ago", "[formula]") {
    const std::string r = date_field().on().weeks_ago(2);
    REQUIRE_THAT(r, ContainsSubstring("\"weeks\""));
    REQUIRE_THAT(r, ContainsSubstring("=2"));
}

TEST_CASE("hours ago", "[formula]") {
    REQUIRE_THAT(date_field().after().hours_ago(24), ContainsSubstring("\"hours\""));
}

TEST_CASE("minutes ago", "[formula]") {
    REQUIRE_THAT(date_field().after().minutes_ago(30), ContainsSubstring("\"minutes\""));
}

TEST_CASE("seconds ago", "[formula]") {
    REQUIRE_THAT(date_field().after().seconds_ago(60), ContainsSubstring("\"seconds\""));
}

TEST_CASE("months ago", "[formula]") {
    REQUIRE_THAT(date_field().before().months_ago(3), ContainsSubstring("\"months\""));
}

TEST_CASE("quarters ago", "[formula]") {
    REQUIRE_THAT(date_field().before().quarters_ago(2), ContainsSubstring("\"quarters\""));
}

TEST_CASE("milliseconds ago", "[formula]") {
    REQUIRE_THAT(date_field().after().milliseconds_ago(500), ContainsSubstring("\"milliseconds\""));
}

TEST_CASE("on or after chain days", "[formula]") {
    REQUIRE_THAT(date_field().on_or_after().days_ago(30), ContainsSubstring("<="));
}

TEST_CASE("on or before chain days", "[formula]") {
    REQUIRE_THAT(date_field().on_or_before().days_ago(30), ContainsSubstring(">="));
}

TEST_CASE("not on chain days", "[formula]") {
    REQUIRE_THAT(date_field().not_on().days_ago(1), ContainsSubstring("!="));
}

TEST_CASE("on chain years", "[formula]") {
    REQUIRE_THAT(date_field().on().years_ago(5), ContainsSubstring("=5"));
}

// ---- Attachment Field ----

TEST_CASE("attachment empty", "[formula]") {
    REQUIRE(attach().is_empty() == "LEN({fldA})=0");
}

TEST_CASE("attachment not empty", "[formula]") {
    REQUIRE(attach().is_not_empty() == "LEN({fldA})>0");
}

TEST_CASE("attachment count", "[formula]") {
    REQUIRE(attach().count(3) == "LEN({fldA})=3");
}

// ---- Lookup Field ----

TEST_CASE("lookup contains wraps in arrayjoin", "[formula]") {
    const std::string r = lookup().contains("groundwork", false, true);
    REQUIRE_THAT(r, ContainsSubstring("ARRAYJOIN({fldClient}"));
    REQUIRE_THAT(r, ContainsSubstring("FIND("));
    REQUIRE_THAT(r, ContainsSubstring("LOWER("));
}

TEST_CASE("lookup starts with wraps in arrayjoin", "[formula]") {
    REQUIRE_THAT(lookup().starts_with("Ground", false, true),
                 ContainsSubstring("ARRAYJOIN({fldClient}"));
}

TEST_CASE("lookup ends with wraps in arrayjoin", "[formula]") {
    const std::string r = lookup().ends_with("BioAg", false, true);
    REQUIRE_THAT(r, ContainsSubstring("ARRAYJOIN({fldClient}"));
    REQUIRE_THAT(r, ContainsSubstring("LEN("));
}

TEST_CASE("lookup eq does not wrap in arrayjoin", "[formula]") {
    // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
    const std::string r = lookup().eq("Groundwork Bio Ag");
    REQUIRE_THAT(r, !ContainsSubstring("ARRAYJOIN"));
    REQUIRE_THAT(r, ContainsSubstring("{fldClient}"));
}

TEST_CASE("lookup not empty does not wrap", "[formula]") {
    REQUIRE_THAT(lookup().is_not_empty(), !ContainsSubstring("ARRAYJOIN"));
}

TEST_CASE("text field unaffected regression", "[formula]") {
    REQUIRE_THAT(FormulaTextField("fldName").contains("hello", false, true),
                 !ContainsSubstring("ARRAYJOIN"));
}

// ---- Date field-to-field comparisons ----

TEST_CASE("on another field", "[formula]") {
    REQUIRE(FormulaDateField("fld123").on(FormulaDateField("fldOther")) ==
            "DATETIME_PARSE({fldOther})=DATETIME_PARSE({fld123})");
}

TEST_CASE("after another field", "[formula]") {
    REQUIRE_THAT(FormulaDateField("fld123").after(FormulaDateField("fldOther")),
                 ContainsSubstring("DATETIME_PARSE({fldOther})<DATETIME_PARSE({fld123})"));
}

TEST_CASE("between mixed operands", "[formula]") {
    const std::string r =
        FormulaDateField("fld123").between("2025-01-01", FormulaDateField("fldOther"));
    REQUIRE_THAT(r, StartsWith("AND("));
    REQUIRE_THAT(r, ContainsSubstring("DATETIME_PARSE('2025-01-01')"));
    REQUIRE_THAT(r, ContainsSubstring("DATETIME_PARSE({fldOther})"));
}

TEST_CASE("string literal still works", "[formula]") {
    const std::string r = FormulaDateField("fld123").on("2025-01-15");
    REQUIRE_THAT(r, ContainsSubstring("DATETIME_PARSE('2025-01-15')"));
    REQUIRE_THAT(r, ContainsSubstring("=DATETIME_PARSE({fld123})"));
}

// ---- Escaping / injection hardening ----

TEST_CASE("quote in value stays inside the string", "[formula]") {
    REQUIRE(FormulaTextField("fldT").eq("a \"quoted\" b") == "{fldT}=\"a \\\"quoted\\\" b\"");
}

TEST_CASE("trailing backslash cannot escape the closing quote", "[formula]") {
    // Pre-fix: ...="x\" left the quote live and leaked formula code.
    REQUIRE(FormulaTextField("fldT").eq("x\\") == "{fldT}=\"x\\\\\"");
}

TEST_CASE("backslash then quote payload is neutralized", "[formula]") {
    const std::string evil = "x\\\", TRUE(), \"";
    const std::string formula = FormulaTextField("fldT").eq(evil);
    const std::string expected = "{fldT}=\"" + Formulas::escape_formula_string(evil) + "\"";
    REQUIRE(formula == expected);
}

TEST_CASE("record id single quote is escaped", "[formula]") {
    REQUIRE(FormulaId().eq("rec' OR TRUE() OR '") == "RECORD_ID()='rec\\' OR TRUE() OR \\''");
}

TEST_CASE("regex backslash survives round trip", "[formula]") {
    // \d -> \\d in formula source; Airtable's string parser unescapes back to \d.
    REQUIRE(FormulaTextField("fldT").regex_match("\\d+") == "REGEX_MATCH({fldT},\"\\\\d+\")");
}

TEST_CASE("phone equals escapes residual quotes", "[formula]") {
    REQUIRE_THAT(FormulaTextField("fldT").phone_equals("555\"1234"), EndsWith("=\"555\\\"1234\""));
}
