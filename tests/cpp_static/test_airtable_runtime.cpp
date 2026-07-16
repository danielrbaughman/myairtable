// Formula-function semantics of the C++ Airtable runtime. Port of the C#
// TestAirtableRuntime suite (184 cases, case-for-case with identical expected
// values). Coercion-helper basics (n/s/a/v/is_truthy) live in
// test_value_coercion.cpp and are not repeated here.
//
// Whole-number results are integral (int64) nodes; nlohmann json equality
// compares numbers semantically (int vs float), mirroring JsonNode.DeepEquals.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <initializer_list>
#include <string>

#include "runtime_array.hpp"
#include "runtime_date.hpp"
#include "runtime_logic.hpp"
#include "runtime_math.hpp"
#include "runtime_regex.hpp"
#include "runtime_string.hpp"

using namespace myairtable;
namespace rt = myairtable::runtime;

namespace {

json i(int64_t v) {
    return json(v);
}

json dbl(double v) {
    return json(v);
}

json str(const char* v) {
    return json(v);
}

json b(bool v) {
    return json(v);
}

json nul() {
    return json(nullptr);
}

json arr(std::initializer_list<json> items) {
    json out = json::array();
    for (const json& item : items) {
        out.push_back(item);
    }
    return out;
}

} // namespace

// ---- Logic ----

TEST_CASE("IfTrue", "[runtime][logic]") {
    REQUIRE(rt::IF(b(true), i(1), i(2)) == i(1));
}

TEST_CASE("IfFalse", "[runtime][logic]") {
    REQUIRE(rt::IF(b(false), i(1), i(2)) == i(2));
}

TEST_CASE("IfNullIsFalse", "[runtime][logic]") {
    REQUIRE(rt::IF(nul(), i(1), i(2)) == i(2));
}

TEST_CASE("IfZeroIsFalsy", "[runtime][logic]") {
    REQUIRE(rt::IF(i(0), str("yes"), str("no")) == str("no"));
}

TEST_CASE("IfNumberIsTruthy", "[runtime][logic]") {
    REQUIRE(rt::IF(i(1), str("yes"), str("no")) == str("yes"));
}

TEST_CASE("IfEmptyStringIsFalsy", "[runtime][logic]") {
    REQUIRE(rt::IF(str(""), str("yes"), str("no")) == str("no"));
}

TEST_CASE("SwitchMatch", "[runtime][logic]") {
    REQUIRE(rt::SWITCH(i(2), nul(), {i(1), str("one"), i(2), str("two")}) == str("two"));
}

TEST_CASE("SwitchDefault", "[runtime][logic]") {
    REQUIRE(rt::SWITCH(i(99), str("other"), {i(1), str("one")}) == str("other"));
}

TEST_CASE("SwitchNoMatchNoDefault", "[runtime][logic]") {
    REQUIRE(rt::SWITCH(i(99), nul(), {i(1), str("one")}) == nul());
}

TEST_CASE("BlankIsNull", "[runtime][logic]") {
    REQUIRE(rt::BLANK() == nul());
}

TEST_CASE("TrueIsBool", "[runtime][logic]") {
    REQUIRE(rt::TRUE() == b(true));
}

TEST_CASE("FalseIsBool", "[runtime][logic]") {
    REQUIRE(rt::FALSE() == b(false));
}

TEST_CASE("IserrorNaN", "[runtime][logic]") {
    REQUIRE(rt::ISERROR(dbl(std::nan(""))) == b(true));
}

TEST_CASE("IserrorNormal", "[runtime][logic]") {
    REQUIRE(rt::ISERROR(i(5)) == b(false));
}

TEST_CASE("IserrorNullIsFalse", "[runtime][logic]") {
    REQUIRE(rt::ISERROR(nul()) == b(false));
    REQUIRE(rt::ISERROR(json(nullptr)) == b(false));
}

TEST_CASE("ErrorIsNaN", "[runtime][logic]") {
    REQUIRE(std::isnan(rt::n(rt::ERROR())));
    REQUIRE(rt::ISERROR(rt::ERROR(str("boom"))) == b(true));
}

// ---- Math ----

TEST_CASE("SumBasic", "[runtime][math]") {
    REQUIRE(rt::SUM({i(1), i(2), i(3)}) == i(6));
}

TEST_CASE("SumWithArray", "[runtime][math]") {
    REQUIRE(rt::SUM({arr({i(1), i(2)}), i(3)}) == i(6));
}

TEST_CASE("SumWithStrings", "[runtime][math]") {
    REQUIRE(rt::SUM({i(1), str("5")}) == i(6));
}

TEST_CASE("AverageBasic", "[runtime][math]") {
    REQUIRE(rt::AVERAGE({i(2), i(4)}) == i(3));
}

TEST_CASE("AverageThree", "[runtime][math]") {
    REQUIRE(rt::AVERAGE({i(10), i(20), i(30)}) == i(20));
}

TEST_CASE("AverageEmptyIsNaN", "[runtime][math]") {
    REQUIRE(std::isnan(rt::n(rt::AVERAGE({}))));
}

TEST_CASE("MinBasic", "[runtime][math]") {
    REQUIRE(rt::MIN({i(3), i(1), i(2)}) == i(1));
}

TEST_CASE("MaxBasic", "[runtime][math]") {
    REQUIRE(rt::MAX({i(3), i(1), i(2)}) == i(3));
}

TEST_CASE("MinEmptyIsNaN", "[runtime][math]") {
    REQUIRE(std::isnan(rt::n(rt::MIN({}))));
}

TEST_CASE("MaxEmptyIsNaN", "[runtime][math]") {
    REQUIRE(std::isnan(rt::n(rt::MAX({}))));
}

TEST_CASE("CountSkipsStrings", "[runtime][math]") {
    REQUIRE(rt::COUNT({i(1), str("x"), i(2)}) == i(2));
}

TEST_CASE("CountSkipsNulls", "[runtime][math]") {
    REQUIRE(rt::COUNT({i(1), str("a"), i(3), nul()}) == i(2));
}

TEST_CASE("CountBoolsNotCounted", "[runtime][math]") {
    REQUIRE(rt::COUNT({b(true), b(false)}) == i(0));
}

TEST_CASE("CountaSkipsNulls", "[runtime][math]") {
    REQUIRE(rt::COUNTA({i(1), nul(), str("")}) == i(1));
}

TEST_CASE("CountaExcludesNullAndEmpty", "[runtime][math]") {
    REQUIRE(rt::COUNTA({i(1), str(""), nul(), str("hi")}) == i(2));
}

TEST_CASE("CountaCountsBools", "[runtime][math]") {
    REQUIRE(rt::COUNTA({b(true), b(false)}) == i(2));
}

TEST_CASE("RoundToInt", "[runtime][math]") {
    REQUIRE(rt::ROUND(dbl(3.7)) == i(4));
}

TEST_CASE("RoundToPrecision", "[runtime][math]") {
    REQUIRE(rt::ROUND(dbl(3.14159), i(2)) == dbl(3.14));
}

TEST_CASE("RoundBasic", "[runtime][math]") {
    REQUIRE(rt::ROUND(dbl(3.456), i(2)) == dbl(3.46));
}

TEST_CASE("RoundHalfAway", "[runtime][math]") {
    REQUIRE(rt::ROUND(dbl(3.5), i(0)) == i(4));
}

TEST_CASE("RoundupInt", "[runtime][math]") {
    REQUIRE(rt::ROUNDUP(dbl(3.1)) == i(4));
}

TEST_CASE("RoundupPrecision", "[runtime][math]") {
    REQUIRE(rt::ROUNDUP(dbl(3.14), i(1)) == dbl(3.2));
}

TEST_CASE("RounddownInt", "[runtime][math]") {
    REQUIRE(rt::ROUNDDOWN(dbl(3.9)) == i(3));
}

TEST_CASE("RounddownPrecision", "[runtime][math]") {
    REQUIRE(rt::ROUNDDOWN(dbl(3.19), i(1)) == dbl(3.1));
}

TEST_CASE("CeilingBasic", "[runtime][math]") {
    REQUIRE(rt::CEILING(dbl(3.2)) == i(4));
}

TEST_CASE("CeilingSignificance", "[runtime][math]") {
    REQUIRE(rt::CEILING(dbl(4.3), i(2)) == i(6));
}

TEST_CASE("CeilingZeroSignificanceDefaultsToOne", "[runtime][math]") {
    REQUIRE(rt::CEILING(dbl(4.3), i(0)) == i(5));
}

TEST_CASE("FloorBasic", "[runtime][math]") {
    REQUIRE(rt::FLOOR(dbl(3.8)) == i(3));
}

TEST_CASE("FloorSignificance", "[runtime][math]") {
    REQUIRE(rt::FLOOR(dbl(4.9), i(2)) == i(4));
}

TEST_CASE("LogBase10", "[runtime][math]") {
    REQUIRE(rt::LOG(i(100)) == i(2));
}

TEST_CASE("LogBase2", "[runtime][math]") {
    REQUIRE(rt::n(rt::LOG(i(8), i(2))) == Catch::Approx(3.0).margin(1e-9));
}

TEST_CASE("EvenRoundsUp", "[runtime][math]") {
    REQUIRE(rt::EVEN(dbl(3.0)) == i(4));
}

TEST_CASE("EvenAlreadyEven", "[runtime][math]") {
    REQUIRE(rt::EVEN(i(4)) == i(4));
}

TEST_CASE("EvenNegative", "[runtime][math]") {
    REQUIRE(rt::EVEN(i(-3)) == i(-4));
}

TEST_CASE("OddRoundsUp", "[runtime][math]") {
    REQUIRE(rt::ODD(dbl(2.0)) == i(3));
}

TEST_CASE("OddAlreadyOdd", "[runtime][math]") {
    REQUIRE(rt::ODD(i(3)) == i(3));
}

TEST_CASE("OddNegative", "[runtime][math]") {
    REQUIRE(rt::ODD(i(-4)) == i(-5));
}

TEST_CASE("ValueString", "[runtime][math]") {
    REQUIRE(rt::VALUE(str("42")) == i(42));
}

TEST_CASE("ValueStringFloat", "[runtime][math]") {
    REQUIRE(rt::VALUE(str("3.14")) == dbl(3.14));
}

TEST_CASE("ValueInvalid", "[runtime][math]") {
    REQUIRE(std::isnan(rt::n(rt::VALUE(str("abc")))));
}

TEST_CASE("ValueNullIsZero", "[runtime][math]") {
    REQUIRE(rt::VALUE(nul()) == i(0));
}

TEST_CASE("PowerBasic", "[runtime][math]") {
    REQUIRE(rt::POWER(i(2), i(3)) == i(8));
}

TEST_CASE("ModBasic", "[runtime][math]") {
    REQUIRE(rt::MOD(i(10), i(3)) == i(1));
}

TEST_CASE("ModNegativeDividendKeepsSign", "[runtime][math]") {
    REQUIRE(rt::MOD(i(-10), i(3)) == i(-1));
}

TEST_CASE("ModDivZeroIsNaN", "[runtime][math]") {
    REQUIRE(std::isnan(rt::n(rt::MOD(i(5), i(0)))));
}

TEST_CASE("AbsNegative", "[runtime][math]") {
    REQUIRE(rt::ABS(i(-5)) == i(5));
}

TEST_CASE("AbsPositive", "[runtime][math]") {
    REQUIRE(rt::ABS(i(5)) == i(5));
}

TEST_CASE("SqrtBasic", "[runtime][math]") {
    REQUIRE(rt::SQRT(i(9)) == i(3));
}

TEST_CASE("ExpBasic", "[runtime][math]") {
    REQUIRE(rt::n(rt::EXP(i(1))) == Catch::Approx(2.718281828459045).margin(1e-9));
}

TEST_CASE("IntTruncates", "[runtime][math]") {
    REQUIRE(rt::INT(dbl(3.7)) == i(3));
}

TEST_CASE("IntNegativeFloors", "[runtime][math]") {
    REQUIRE(rt::INT(dbl(-3.2)) == i(-4));
}

// ---- String ----

TEST_CASE("LenString", "[runtime][string]") {
    REQUIRE(rt::LEN(str("hello")) == i(5));
}

TEST_CASE("LenEmpty", "[runtime][string]") {
    REQUIRE(rt::LEN(str("")) == i(0));
}

TEST_CASE("LenUnicode", "[runtime][string]") {
    REQUIRE(rt::LEN(str("café")) == i(4));
}

TEST_CASE("LeftBasic", "[runtime][string]") {
    REQUIRE(rt::LEFT(str("hello"), i(3)) == str("hel"));
}

TEST_CASE("LeftZero", "[runtime][string]") {
    REQUIRE(rt::LEFT(str("hello"), i(0)) == str(""));
}

TEST_CASE("LeftExceeds", "[runtime][string]") {
    REQUIRE(rt::LEFT(str("hi"), i(5)) == str("hi"));
}

TEST_CASE("RightBasic", "[runtime][string]") {
    REQUIRE(rt::RIGHT(str("hello"), i(3)) == str("llo"));
}

TEST_CASE("RightExceeds", "[runtime][string]") {
    REQUIRE(rt::RIGHT(str("hi"), i(5)) == str("hi"));
}

TEST_CASE("MidBasic", "[runtime][string]") {
    REQUIRE(rt::MID(str("hello"), i(2), i(3)) == str("ell"));
}

TEST_CASE("MidStartOne", "[runtime][string]") {
    REQUIRE(rt::MID(str("hello"), i(1), i(2)) == str("he"));
}

TEST_CASE("MidStartPastEndIsEmpty", "[runtime][string]") {
    REQUIRE(rt::MID(str("hello"), i(10), i(3)) == str(""));
}

TEST_CASE("FindFound", "[runtime][string]") {
    REQUIRE(rt::FIND(str("l"), str("hello")) == i(3));
}

TEST_CASE("FindMultiChar", "[runtime][string]") {
    REQUIRE(rt::FIND(str("ll"), str("hello")) == i(3));
}

TEST_CASE("FindNotFound", "[runtime][string]") {
    REQUIRE(rt::FIND(str("z"), str("hello")) == i(0));
}

TEST_CASE("FindCaseSensitive", "[runtime][string]") {
    REQUIRE(rt::FIND(str("LL"), str("hello")) == i(0));
}

TEST_CASE("FindWithStart", "[runtime][string]") {
    REQUIRE(rt::FIND(str("l"), str("hello"), i(4)) == i(4));
}

TEST_CASE("FindStartPastEndIsZero", "[runtime][string]") {
    REQUIRE(rt::FIND(str("l"), str("hello"), i(10)) == i(0));
}

TEST_CASE("FindUnicode", "[runtime][string]") {
    REQUIRE(rt::FIND(str("f"), str("café")) == i(3));
    REQUIRE(rt::FIND(str("é"), str("café"), i(4)) == i(4));
}

TEST_CASE("SearchCaseInsensitive", "[runtime][string]") {
    REQUIRE(rt::SEARCH(str("L"), str("hello")) == i(3));
}

TEST_CASE("SearchMultiChar", "[runtime][string]") {
    REQUIRE(rt::SEARCH(str("LL"), str("hello")) == i(3));
}

TEST_CASE("SearchWithStart", "[runtime][string]") {
    REQUIRE(rt::SEARCH(str("l"), str("hello"), i(4)) == i(4));
}

TEST_CASE("SubstituteAll", "[runtime][string]") {
    REQUIRE(rt::SUBSTITUTE(str("a-b-c"), str("-"), str("_")) == str("a_b_c"));
}

TEST_CASE("SubstituteAllOverlapping", "[runtime][string]") {
    REQUIRE(rt::SUBSTITUTE(str("aaa"), str("a"), str("b")) == str("bbb"));
}

TEST_CASE("SubstituteNth", "[runtime][string]") {
    REQUIRE(rt::SUBSTITUTE(str("a-b-c"), str("-"), str("_"), i(2)) == str("a-b_c"));
}

TEST_CASE("SubstituteNthRepeated", "[runtime][string]") {
    REQUIRE(rt::SUBSTITUTE(str("aaa"), str("a"), str("b"), i(2)) == str("aba"));
}

TEST_CASE("SubstituteEmptyOldIsNoop", "[runtime][string]") {
    REQUIRE(rt::SUBSTITUTE(str("hello"), str(""), str("x")) == str("hello"));
}

TEST_CASE("ReplaceBasic", "[runtime][string]") {
    REQUIRE(rt::REPLACE(str("hello"), i(2), i(3), str("XX")) == str("hXXo"));
}

TEST_CASE("ReplacePastEndAppends", "[runtime][string]") {
    REQUIRE(rt::REPLACE(str("hi"), i(10), i(2), str("X")) == str("hiX"));
}

TEST_CASE("LowerBasic", "[runtime][string]") {
    REQUIRE(rt::LOWER(str("HI")) == str("hi"));
}

TEST_CASE("UpperBasic", "[runtime][string]") {
    REQUIRE(rt::UPPER(str("hi")) == str("HI"));
}

TEST_CASE("TrimBasic", "[runtime][string]") {
    REQUIRE(rt::TRIM(str("  x  ")) == str("x"));
}

TEST_CASE("TrimNoExtra", "[runtime][string]") {
    REQUIRE(rt::TRIM(str("hello")) == str("hello"));
}

TEST_CASE("ReptBasic", "[runtime][string]") {
    REQUIRE(rt::REPT(str("ab"), i(3)) == str("ababab"));
}

TEST_CASE("ReptZero", "[runtime][string]") {
    REQUIRE(rt::REPT(str("ab"), i(0)) == str(""));
}

TEST_CASE("ConcatenateBasic", "[runtime][string]") {
    REQUIRE(rt::CONCATENATE({str("a"), i(1), str("b")}) == str("a1b"));
}

TEST_CASE("ConcatenateWithNumbers", "[runtime][string]") {
    REQUIRE(rt::CONCATENATE({str("count: "), i(5)}) == str("count: 5"));
}

TEST_CASE("TString", "[runtime][string]") {
    REQUIRE(rt::T(str("hello")) == str("hello"));
}

TEST_CASE("TNumberIsEmpty", "[runtime][string]") {
    REQUIRE(rt::T(i(42)) == str(""));
}

TEST_CASE("TNullIsEmpty", "[runtime][string]") {
    REQUIRE(rt::T(nul()) == str(""));
}

TEST_CASE("EncodeUrlComponentSpace", "[runtime][string]") {
    REQUIRE(rt::ENCODE_URL_COMPONENT(str("hello world")) == str("hello%20world"));
}

TEST_CASE("EncodeUrlComponentPercent", "[runtime][string]") {
    REQUIRE(rt::ENCODE_URL_COMPONENT(str("100%")) == str("100%25"));
}

TEST_CASE("EncodeUrlComponentEncodesReservedChars", "[runtime][string]") {
    // encodeURIComponent (which Airtable matches) percent-encodes reserved chars like & = + .
    REQUIRE(rt::ENCODE_URL_COMPONENT(str("a&b=c")) == str("a%26b%3Dc"));
    REQUIRE(rt::ENCODE_URL_COMPONENT(str("a+b")) == str("a%2Bb"));
}

TEST_CASE("EncodeUrlComponentUnicode", "[runtime][string]") {
    REQUIRE(rt::ENCODE_URL_COMPONENT(str("café")) == str("caf%C3%A9"));
}

// ---- Date/time ----

TEST_CASE("YearOfIsoDate", "[runtime][date]") {
    REQUIRE(rt::YEAR(str("2025-04-20T10:00:00Z")) == i(2025));
}

TEST_CASE("YearOfNullIsZero", "[runtime][date]") {
    REQUIRE(rt::YEAR(nul()) == i(0));
}

TEST_CASE("MonthOfIsoDate", "[runtime][date]") {
    REQUIRE(rt::MONTH(str("2025-04-20T10:00:00Z")) == i(4));
}

TEST_CASE("DayOfIsoDate", "[runtime][date]") {
    REQUIRE(rt::DAY(str("2025-04-20T10:00:00Z")) == i(20));
}

TEST_CASE("HourOfIsoDate", "[runtime][date]") {
    REQUIRE(rt::HOUR(str("2025-04-20T10:30:00Z")) == i(10));
}

TEST_CASE("MinuteBasic", "[runtime][date]") {
    REQUIRE(rt::MINUTE(str("2024-01-15T14:30:00Z")) == i(30));
}

TEST_CASE("SecondBasic", "[runtime][date]") {
    REQUIRE(rt::SECOND(str("2024-01-15T14:30:45Z")) == i(45));
}

TEST_CASE("WeekdaySunday", "[runtime][date]") {
    REQUIRE(rt::WEEKDAY(str("2024-01-14T00:00:00Z")) == i(0));
}

TEST_CASE("WeekdayMonday", "[runtime][date]") {
    REQUIRE(rt::WEEKDAY(str("2024-01-15T00:00:00Z")) == i(1));
}

TEST_CASE("WeekdaySaturday", "[runtime][date]") {
    REQUIRE(rt::WEEKDAY(str("2024-01-20T00:00:00Z")) == i(6));
}

TEST_CASE("WeeknumBasic", "[runtime][date]") {
    REQUIRE(rt::WEEKNUM(str("2024-01-15T00:00:00Z")) == i(3));
}

TEST_CASE("DatetimeDiffDays", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2025-04-20T00:00:00Z"), str("2025-04-15T00:00:00Z"),
                              str("days")) == i(5));
}

TEST_CASE("DatetimeDiffHours", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2025-04-20T12:00:00Z"), str("2025-04-20T00:00:00Z"),
                              str("hours")) == i(12));
}

TEST_CASE("DatetimeDiffMinutes", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2024-01-15T13:30:00Z"), str("2024-01-15T12:00:00Z"),
                              str("minutes")) == i(90));
}

TEST_CASE("DatetimeDiffWeeks", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2024-01-29T00:00:00Z"), str("2024-01-15T00:00:00Z"),
                              str("weeks")) == i(2));
}

TEST_CASE("DatetimeDiffMonths", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2024-03-15T00:00:00Z"), str("2024-01-15T00:00:00Z"),
                              str("months")) == i(2));
}

TEST_CASE("DatetimeDiffYears", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2025-01-15T00:00:00Z"), str("2024-06-15T00:00:00Z"),
                              str("years")) == i(1));
}

TEST_CASE("DatetimeDiffDefaultDays", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(str("2024-01-20T00:00:00Z"), str("2024-01-15T00:00:00Z")) == i(5));
}

TEST_CASE("DatetimeDiffNullIsZero", "[runtime][date]") {
    REQUIRE(rt::DATETIME_DIFF(nul(), str("2024-01-15T00:00:00Z"), str("days")) == i(0));
}

TEST_CASE("DateaddDays", "[runtime][date]") {
    REQUIRE(rt::DATEADD(str("2024-01-15T00:00:00Z"), i(5), str("days")) ==
            str("2024-01-20T00:00:00.000Z"));
}

TEST_CASE("DateaddMonthsClamp", "[runtime][date]") {
    REQUIRE(rt::DATEADD(str("2024-01-31T00:00:00Z"), i(1), str("months")) ==
            str("2024-02-29T00:00:00.000Z"));
}

TEST_CASE("DateaddYears", "[runtime][date]") {
    REQUIRE(rt::DATEADD(str("2024-01-15T00:00:00Z"), i(1), str("years")) ==
            str("2025-01-15T00:00:00.000Z"));
}

TEST_CASE("DateaddHours", "[runtime][date]") {
    REQUIRE(rt::DATEADD(str("2024-01-15T12:00:00Z"), i(3), str("hours")) ==
            str("2024-01-15T15:00:00.000Z"));
}

TEST_CASE("DateaddNullIsNull", "[runtime][date]") {
    REQUIRE(rt::DATEADD(nul(), i(5), str("days")) == nul());
}

TEST_CASE("IsSameSameDay", "[runtime][date]") {
    REQUIRE(rt::IS_SAME(str("2025-04-20T10:00:00Z"), str("2025-04-20T15:00:00Z"), str("days")) ==
            b(true));
}

TEST_CASE("IsSameFalse", "[runtime][date]") {
    REQUIRE(rt::IS_SAME(str("2024-01-15T00:00:00Z"), str("2024-01-16T00:00:00Z"), str("days")) ==
            b(false));
}

TEST_CASE("IsBeforeDay", "[runtime][date]") {
    REQUIRE(rt::IS_BEFORE(str("2025-04-20T10:00:00Z"), str("2025-04-21T10:00:00Z"), str("days")) ==
            b(true));
}

TEST_CASE("IsBeforeFalseWhenAfter", "[runtime][date]") {
    REQUIRE(rt::IS_BEFORE(str("2025-04-22T10:00:00Z"), str("2025-04-21T10:00:00Z"), str("days")) ==
            b(false));
}

TEST_CASE("IsAfterTrue", "[runtime][date]") {
    REQUIRE(rt::IS_AFTER(str("2024-01-16T00:00:00Z"), str("2024-01-15T00:00:00Z"), str("days")) ==
            b(true));
}

TEST_CASE("WorkdayBasic", "[runtime][date]") {
    REQUIRE(rt::WORKDAY(str("2024-01-15T00:00:00Z"), i(5)) == str("2024-01-22T00:00:00.000Z"));
}

TEST_CASE("WorkdaySkipWeekend", "[runtime][date]") {
    REQUIRE(rt::WORKDAY(str("2024-01-19T00:00:00Z"), i(1)) == str("2024-01-22T00:00:00.000Z"));
}

TEST_CASE("WorkdayNegative", "[runtime][date]") {
    REQUIRE(rt::WORKDAY(str("2024-01-22T00:00:00Z"), i(-1)) == str("2024-01-19T00:00:00.000Z"));
}

TEST_CASE("WorkdayNullIsNull", "[runtime][date]") {
    REQUIRE(rt::WORKDAY(nul(), i(5)) == nul());
}

TEST_CASE("WorkdayDiffBasic", "[runtime][date]") {
    REQUIRE(rt::WORKDAY_DIFF(str("2024-01-15T00:00:00Z"), str("2024-01-22T00:00:00Z")) == i(6));
}

TEST_CASE("WorkdayDiffReverseIsNegative", "[runtime][date]") {
    REQUIRE(rt::WORKDAY_DIFF(str("2024-01-22T00:00:00Z"), str("2024-01-15T00:00:00Z")) == i(-6));
}

TEST_CASE("WorkdayDiffNullIsZero", "[runtime][date]") {
    REQUIRE(rt::WORKDAY_DIFF(nul(), str("2024-01-15T00:00:00Z")) == i(0));
}

TEST_CASE("SetTimezoneBasic", "[runtime][date]") {
    REQUIRE(rt::SET_TIMEZONE(str("2024-01-15T12:00:00Z"), str("America/New_York")) ==
            str("2024-01-15T07:00:00.000Z"));
}

TEST_CASE("SetTimezoneInvalidZoneReturnsIso", "[runtime][date]") {
    REQUIRE(rt::SET_TIMEZONE(str("2024-01-15T12:00:00Z"), str("Not/AZone")) ==
            str("2024-01-15T12:00:00.000Z"));
}

TEST_CASE("DatetimeFormatDefault", "[runtime][date]") {
    REQUIRE(rt::DATETIME_FORMAT(str("2024-01-15T14:30:00Z")) == str("2024-01-15T14:30:00.000Z"));
}

TEST_CASE("DatetimeFormatCustomDate", "[runtime][date]") {
    REQUIRE(rt::DATETIME_FORMAT(str("2024-01-15T14:30:00Z"), str("YYYY-MM-DD")) ==
            str("2024-01-15"));
}

TEST_CASE("DatetimeFormatTime", "[runtime][date]") {
    REQUIRE(rt::DATETIME_FORMAT(str("2024-01-15T14:30:00Z"), str("HH:mm")) == str("14:30"));
}

TEST_CASE("DatetimeFormatNullIsEmpty", "[runtime][date]") {
    REQUIRE(rt::DATETIME_FORMAT(nul(), str("YYYY-MM-DD")) == str(""));
}

TEST_CASE("DatestrBasic", "[runtime][date]") {
    REQUIRE(rt::DATESTR(str("2024-01-15T14:30:00Z")) == str("2024-01-15"));
}

TEST_CASE("DatestrNullIsEmpty", "[runtime][date]") {
    REQUIRE(rt::DATESTR(nul()) == str(""));
}

TEST_CASE("TimestrBasic", "[runtime][date]") {
    REQUIRE(rt::TIMESTR(str("2024-01-15T14:30:00Z")) == str("14:30:00"));
}

TEST_CASE("DatetimeParseBasic", "[runtime][date]") {
    REQUIRE(rt::DATETIME_PARSE(str("2024-01-15")) == str("2024-01-15T00:00:00.000Z"));
}

TEST_CASE("DatetimeParseGarbageIsNull", "[runtime][date]") {
    REQUIRE(rt::DATETIME_PARSE(str("not a date")) == nul());
}

TEST_CASE("NowIsParseableIso", "[runtime][date]") {
    REQUIRE(rt::d(rt::NOW()).has_value());
}

TEST_CASE("TodayIsParseableIso", "[runtime][date]") {
    REQUIRE(rt::d(rt::TODAY()).has_value());
}

TEST_CASE("TonowWithUnitIsPositiveForPastDate", "[runtime][date]") {
    REQUIRE(rt::n(rt::TONOW(str("2000-01-01T00:00:00Z"), str("days"))) > 0);
}

TEST_CASE("FromnowWithUnitIsNegativeForPastDate", "[runtime][date]") {
    REQUIRE(rt::n(rt::FROMNOW(str("2000-01-01T00:00:00Z"), str("days"))) < 0);
}

TEST_CASE("TonowHumanDurationForOldDateIsYears", "[runtime][date]") {
    REQUIRE(rt::s(rt::TONOW(str("2000-01-01T00:00:00Z"))).ends_with("years"));
}

// ---- Array ----

TEST_CASE("ArrayJoinDefault", "[runtime][array]") {
    REQUIRE(rt::ARRAYJOIN(arr({i(1), i(2), i(3)})) == str("1, 2, 3"));
}

TEST_CASE("ArrayJoinCustomSep", "[runtime][array]") {
    REQUIRE(rt::ARRAYJOIN(arr({i(1), i(2)}), str("-")) == str("1-2"));
}

TEST_CASE("ArrayJoinNonArray", "[runtime][array]") {
    REQUIRE(rt::ARRAYJOIN(str("hello")) == str("hello"));
}

TEST_CASE("ArrayJoinNullIsEmpty", "[runtime][array]") {
    REQUIRE(rt::ARRAYJOIN(nul()) == str(""));
}

TEST_CASE("ArrayUniqueBasic", "[runtime][array]") {
    REQUIRE(rt::ARRAYUNIQUE(arr({i(1), i(2), i(1), i(3)})) == arr({i(1), i(2), i(3)}));
}

TEST_CASE("ArrayUniquePreservesOrder", "[runtime][array]") {
    REQUIRE(rt::ARRAYUNIQUE(arr({i(3), i(1), i(2), i(1), i(3)})) == arr({i(3), i(1), i(2)}));
}

TEST_CASE("ArrayCompactStripsNullsAndEmptyStrings", "[runtime][array]") {
    REQUIRE(rt::ARRAYCOMPACT(arr({i(1), nul(), str(""), i(2)})) == arr({i(1), i(2)}));
}

TEST_CASE("ArrayCompactKeepsZeroAndFalse", "[runtime][array]") {
    REQUIRE(rt::ARRAYCOMPACT(arr({i(0), nul(), b(false), str("")})) == arr({i(0), b(false)}));
}

TEST_CASE("ArrayCompactNullInputIsEmptyArray", "[runtime][array]") {
    REQUIRE(rt::ARRAYCOMPACT(nul()) == arr({}));
}

TEST_CASE("ArrayFlattenNested", "[runtime][array]") {
    REQUIRE(rt::ARRAYFLATTEN(arr({i(1), arr({i(2), i(3)}), i(4)})) ==
            arr({i(1), i(2), i(3), i(4)}));
}

TEST_CASE("ArrayFlattenDeep", "[runtime][array]") {
    REQUIRE(rt::ARRAYFLATTEN(arr({i(1), arr({i(2), arr({i(3), i(4)})})})) ==
            arr({i(1), i(2), i(3), i(4)}));
}

TEST_CASE("ArrayFlattenAlreadyFlat", "[runtime][array]") {
    REQUIRE(rt::ARRAYFLATTEN(arr({i(1), i(2), i(3)})) == arr({i(1), i(2), i(3)}));
}

TEST_CASE("ArrayFlattenNonArrayWraps", "[runtime][array]") {
    REQUIRE(rt::ARRAYFLATTEN(i(5)) == arr({i(5)}));
}

// ---- Regex ----

TEST_CASE("RegexMatchTrue", "[runtime][regex]") {
    REQUIRE(rt::REGEX_MATCH(str("hello"), str("^hel")) == b(true));
}

TEST_CASE("RegexMatchFalse", "[runtime][regex]") {
    REQUIRE(rt::REGEX_MATCH(str("hello"), str("^xyz")) == b(false));
}

TEST_CASE("RegexMatchUnanchored", "[runtime][regex]") {
    REQUIRE(rt::REGEX_MATCH(str("Hello"), str("^.e")) == b(true));
}

TEST_CASE("RegexMatchInvalidPatternIsFalse", "[runtime][regex]") {
    REQUIRE(rt::REGEX_MATCH(str("hello"), str("(")) == b(false));
}

TEST_CASE("RegexExtractBasic", "[runtime][regex]") {
    REQUIRE(rt::REGEX_EXTRACT(str("hello123"), str("\\d+")) == str("123"));
}

TEST_CASE("RegexExtractFirstMatch", "[runtime][regex]") {
    REQUIRE(rt::REGEX_EXTRACT(str("Hello"), str("[aeiou]")) == str("e"));
}

TEST_CASE("RegexExtractNoMatchIsEmptyString", "[runtime][regex]") {
    REQUIRE(rt::REGEX_EXTRACT(str("xyz"), str("[aeiou]")) == str(""));
}

TEST_CASE("RegexReplaceBasic", "[runtime][regex]") {
    REQUIRE(rt::REGEX_REPLACE(str("hello"), str("l+"), str("x")) == str("hexo"));
}

TEST_CASE("RegexReplaceAllOccurrences", "[runtime][regex]") {
    REQUIRE(rt::REGEX_REPLACE(str("Hello"), str("[aeiou]"), str("*")) == str("H*ll*"));
}
