package airtable

// Parity unit tests for the formula runtime, ported case-by-case from
// tests/test_airtable_runtime.rs. The Rust suite operates on serde_json::Value;
// the Go runtime operates on native `any` (nil/bool/float64/string/[]any). JSON
// number literals (json!(6)) port to float64(6); numeric runtime results are
// float64, so we compare with float64 expectations and use a shared eq helper
// for slices/arrays.

import (
	"math"
	"reflect"
	"testing"
)

// arr builds a native []any (the decoded-JSON array form). Always non-nil so an
// empty array compares equal to the runtime's `[]any{}` (not a nil slice).
func arr(xs ...any) []any {
	out := make([]any, 0, len(xs))
	return append(out, xs...)
}

// eq is the shared deep-equality assertion used across cases.
func eq(t *testing.T, name string, got, want any) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: got %#v (%T), want %#v (%T)", name, got, got, want, want)
	}
}

// =============================================================================
// Type Coercion — N()
// =============================================================================

func TestN(t *testing.T) {
	eq(t, "n_null", N(nil), 0.0)
	eq(t, "n_true", N(true), 1.0)
	eq(t, "n_false", N(false), 0.0)
	eq(t, "n_int", N(42.0), 42.0)
	eq(t, "n_float", N(3.14), 3.14)
	eq(t, "n_string_int", N("5"), 5.0)
	eq(t, "n_string_float", N("3.14"), 3.14)
	eq(t, "n_string_invalid", N("abc"), 0.0)
	eq(t, "n_array_first", N(arr(5.0, 10.0)), 5.0)
	eq(t, "n_array_empty", N(arr()), 0.0)
}

// =============================================================================
// Type Coercion — S()
// =============================================================================

func TestS(t *testing.T) {
	eq(t, "s_null", S(nil), "")
	eq(t, "s_true", S(true), "1")
	eq(t, "s_false", S(false), "0")
	eq(t, "s_whole_float", S(15.0), "15")
	eq(t, "s_fractional_float", S(2.5), "2.5")
	eq(t, "s_int", S(42.0), "42")
	eq(t, "s_string", S("hello"), "hello")
	eq(t, "s_array_join", S(arr("hello", "world")), "hello, world")
}

// =============================================================================
// Type Coercion — A() / AN() / AS()
// =============================================================================

func TestAFamily(t *testing.T) {
	eq(t, "a_flattens_one_level", A(1.0, arr(2.0, 3.0), 4.0), arr(1.0, 2.0, 3.0, 4.0))
	// NOTE: the Go runtime (matching Java) drops nil args during flattening; the
	// Rust reference instead keeps nulls and coerces them. We pin the Go/Java
	// contract (verified by value_coercion_test.go), so the nil is dropped.
	eq(t, "an_coerces_to_numbers", AN(1.0, "5", nil), []float64{1.0, 5.0})
	eq(t, "as_coerces_to_strings", AS(1.0, "hello", nil), []string{"1", "hello"})
}

// =============================================================================
// Math Functions
// =============================================================================

func TestMath(t *testing.T) {
	eq(t, "sum_basic", SUM(1.0, 2.0, 3.0), 6.0)
	eq(t, "sum_with_strings", SUM(1.0, "5"), 6.0)

	eq(t, "average_basic", AVERAGE(10.0, 20.0, 30.0), 20.0)
	if v := AVERAGE(); !math.IsNaN(N(v)) {
		t.Errorf("average_empty: got %v want NaN", v)
	}

	eq(t, "count_numbers_only", COUNT(1.0, "a", 3.0, nil), 2.0)
	eq(t, "count_bools_not_counted", COUNT(true, false), 0.0)

	eq(t, "counta_excludes_null_and_empty", COUNTA(1.0, "", nil, "hi"), 2.0)
	eq(t, "counta_counts_bools", COUNTA(true, false), 2.0)

	eq(t, "min_basic", MIN(5.0, 2.0, 8.0), 2.0)
	eq(t, "max_basic", MAX(5.0, 2.0, 8.0), 8.0)

	eq(t, "round_basic", ROUND(3.456, 2.0), 3.46)
	eq(t, "round_zero", ROUND(3.5, 0.0), 4.0)

	eq(t, "roundup_basic", ROUNDUP(3.14, 1.0), 3.2)
	eq(t, "rounddown_basic", ROUNDDOWN(3.19, 1.0), 3.1)

	eq(t, "ceiling_basic", CEILING(4.3, 2.0), 6.0)
	eq(t, "ceiling_default", CEILING(4.3, 0.0), 5.0)

	eq(t, "floor_basic", FLOOR(4.9, 2.0), 4.0)

	eq(t, "log_base10", LOG(100.0), 2.0)
	eq(t, "log_base2", LOG(8.0, 2.0), 3.0)

	eq(t, "even_positive", EVEN(3.0), 4.0)
	eq(t, "even_already_even", EVEN(4.0), 4.0)
	eq(t, "even_negative", EVEN(-3.0), -4.0)

	eq(t, "odd_positive", ODD(4.0), 5.0)
	eq(t, "odd_already_odd", ODD(3.0), 3.0)
	eq(t, "odd_negative", ODD(-4.0), -5.0)

	eq(t, "value_string_number", VALUE("42"), 42.0)
	eq(t, "value_string_float", VALUE("3.14"), 3.14)
	if v := VALUE("abc"); !math.IsNaN(N(v)) {
		t.Errorf("value_invalid: got %v want NaN", v)
	}
	eq(t, "value_null", VALUE(nil), 0.0)

	eq(t, "power_basic", POWER(2.0, 3.0), 8.0)
	eq(t, "mod_basic", MOD(10.0, 3.0), 1.0)
	eq(t, "abs_negative", ABS(-5.0), 5.0)
	eq(t, "sqrt_basic", SQRT(9.0), 3.0)
	eq(t, "int_truncates", INT(3.9), 3.0)
	eq(t, "int_negative", INT(-3.9), -4.0) // INT = floor, so -3.9 -> -4

	// EXP pin: EXP(1.0) must equal math.E exactly.
	if v := EXP(1.0); v.(float64) != math.E {
		t.Errorf("exp_pin: EXP(1.0) = %v, want math.E = %v", v, math.E)
	}
	if math.Abs(N(EXP(1.0))-math.E) > 0.0001 {
		t.Errorf("exp_basic: not near E")
	}
}

// =============================================================================
// Logic Functions
// =============================================================================

func TestLogic(t *testing.T) {
	eq(t, "if_true", IF(true, "yes", "no"), "yes")
	eq(t, "if_false", IF(false, "yes", "no"), "no")
	eq(t, "if_null_is_falsy", IF(nil, "yes", "no"), "no")
	eq(t, "if_zero_is_falsy", IF(0.0, "yes", "no"), "no")
	eq(t, "if_number_is_truthy", IF(1.0, "yes", "no"), "yes")
	eq(t, "if_empty_string_is_falsy", IF("", "yes", "no"), "no")

	eq(t, "switch_match", SWITCH(2.0, nil, 1.0, "one", 2.0, "two"), "two")
	eq(t, "switch_default", SWITCH(99.0, "other", 1.0, "one"), "other")
	eq(t, "switch_no_match_no_default", SWITCH(99.0, nil, 1.0, "one"), nil)

	eq(t, "ifs_first_match", IFS(false, "a", true, "b"), "b")
	eq(t, "ifs_no_match", IFS(false, "a", false, "b"), nil)

	eq(t, "and_true", AND(true, 1.0, "x"), true)
	eq(t, "and_false", AND(true, 0.0), false)
	eq(t, "or_true", OR(false, 0.0, "x"), true)
	eq(t, "or_false", OR(false, 0.0, ""), false)
	eq(t, "not_true", NOT(false), true)
	eq(t, "not_false", NOT(1.0), false)
	eq(t, "xor_odd", XOR(true, false, true, true), true)
	eq(t, "xor_even", XOR(true, true), false)

	eq(t, "blank_is_null", BLANK(), nil)
	eq(t, "true_is_bool", TRUE(), true)
	eq(t, "false_is_bool", FALSE(), false)

	eq(t, "iserror_null", ISERROR(nil), false) // nil is not a NaN number
	eq(t, "iserror_nan", ISERROR(math.NaN()), true)
	eq(t, "iserror_number", ISERROR(5.0), false)
	if v := ERROR(); !math.IsNaN(N(v)) {
		t.Errorf("error_is_nan: got %v", v)
	}

	// is_truthy direct cases
	eq(t, "truthy_null", IsTruthy(nil), false)
	eq(t, "truthy_false", IsTruthy(false), false)
	eq(t, "truthy_zero", IsTruthy(0.0), false)
	eq(t, "truthy_empty", IsTruthy(""), false)
	eq(t, "truthy_true", IsTruthy(true), true)
	eq(t, "truthy_one", IsTruthy(1.0), true)
	eq(t, "truthy_hello", IsTruthy("hello"), true)
	eq(t, "truthy_array", IsTruthy(arr(1.0)), true)
}

// =============================================================================
// String Functions
// =============================================================================

func TestString(t *testing.T) {
	eq(t, "left_basic", LEFT("hello", 3.0), "hel")
	eq(t, "left_zero", LEFT("hello", 0.0), "")
	eq(t, "left_exceeds", LEFT("hi", 5.0), "hi")

	eq(t, "right_basic", RIGHT("hello", 3.0), "llo")
	eq(t, "right_exceeds", RIGHT("hi", 5.0), "hi")

	eq(t, "mid_basic", MID("hello", 2.0, 3.0), "ell")
	eq(t, "mid_start_one", MID("hello", 1.0, 2.0), "he")

	eq(t, "find_basic", FIND("ll", "hello"), 3.0)
	eq(t, "find_not_found", FIND("xyz", "hello"), 0.0)
	eq(t, "find_case_sensitive", FIND("LL", "hello"), 0.0)
	eq(t, "find_with_start", FIND("l", "hello", 4.0), 4.0)
	eq(t, "find_unicode_f", FIND("f", "café"), 3.0)
	eq(t, "find_unicode_e", FIND("é", "café", 4.0), 4.0)

	eq(t, "search_case_insensitive", SEARCH("LL", "hello"), 3.0)
	eq(t, "search_with_start", SEARCH("l", "hello", 4.0), 4.0)

	eq(t, "substitute_all", SUBSTITUTE("aaa", "a", "b"), "bbb")
	eq(t, "substitute_nth", SUBSTITUTE("aaa", "a", "b", 2.0), "aba")
	eq(t, "substitute_empty_old", SUBSTITUTE("hello", "", "x"), "hello")

	eq(t, "replace_basic", REPLACE("hello", 2.0, 3.0, "XY"), "hXYo")

	eq(t, "t_string", T("hello"), "hello")
	eq(t, "t_number", T(42.0), "")
	eq(t, "t_null", T(nil), "")

	eq(t, "lower_basic", LOWER("Hello"), "hello")
	eq(t, "upper_basic", UPPER("hello"), "HELLO")

	eq(t, "trim_basic", TRIM("  hello  "), "hello")
	eq(t, "trim_no_extra", TRIM("hello"), "hello")

	eq(t, "len_basic", LEN("hello"), 5.0)
	eq(t, "len_empty", LEN(""), 0.0)

	eq(t, "rept_basic", REPT("ab", 3.0), "ababab")
	eq(t, "rept_zero", REPT("ab", 0.0), "")

	eq(t, "concatenate_basic", CONCATENATE("a", "b", "c"), "abc")
	eq(t, "concatenate_with_numbers", CONCATENATE("count: ", 5.0), "count: 5")

	eq(t, "encode_url_component_basic", ENCODE_URL_COMPONENT("hello world"), "hello%20world")
	eq(t, "encode_url_component_special", ENCODE_URL_COMPONENT("a&b=c"), "a%26b%3Dc")
}

// =============================================================================
// Date/Time Functions
// =============================================================================

func TestDate(t *testing.T) {
	// D coercion
	if d := D("2024-01-15T12:00:00Z"); d.IsZero() {
		t.Errorf("d_iso_string: zero")
	} else if got := d.Format("2006-01-02T15:04:05Z07:00"); got != "2024-01-15T12:00:00Z" {
		t.Errorf("d_iso_string: got %s", got)
	}
	if d := D("2024-01-15"); d.IsZero() {
		t.Errorf("d_date_only: zero")
	} else if got := d.Format("2006-01-02T15:04:05Z07:00"); got != "2024-01-15T00:00:00Z" {
		t.Errorf("d_date_only: got %s", got)
	}
	if D(1705312800.0).IsZero() {
		t.Errorf("d_timestamp: zero")
	}
	if !D(nil).IsZero() {
		t.Errorf("d_null: not zero")
	}
	if !D("").IsZero() {
		t.Errorf("d_empty_string: not zero")
	}

	eq(t, "dateadd_days", DATEADD("2024-01-15T00:00:00Z", 5.0, "days"), "2024-01-20T00:00:00.000Z")
	eq(t, "dateadd_months_clamp", DATEADD("2024-01-31T00:00:00Z", 1.0, "months"), "2024-02-29T00:00:00.000Z")
	eq(t, "dateadd_years", DATEADD("2024-01-15T00:00:00Z", 1.0, "years"), "2025-01-15T00:00:00.000Z")
	eq(t, "dateadd_hours", DATEADD("2024-01-15T12:00:00Z", 3.0, "hours"), "2024-01-15T15:00:00.000Z")
	eq(t, "dateadd_null", DATEADD(nil, 5.0, "days"), nil)

	eq(t, "datetime_diff_days", DATETIME_DIFF("2024-01-20T00:00:00Z", "2024-01-15T00:00:00Z", "days"), 5.0)
	eq(t, "datetime_diff_hours", DATETIME_DIFF("2024-01-15T15:00:00Z", "2024-01-15T12:00:00Z", "hours"), 3.0)
	eq(t, "datetime_diff_months", DATETIME_DIFF("2024-03-15T00:00:00Z", "2024-01-15T00:00:00Z", "months"), 2.0)
	eq(t, "datetime_diff_default_days", DATETIME_DIFF("2024-01-20T00:00:00Z", "2024-01-15T00:00:00Z"), 5.0)
	eq(t, "datetime_diff_null", DATETIME_DIFF(nil, "2024-01-15T00:00:00Z", "days"), 0.0)

	eq(t, "datetime_format_default", DATETIME_FORMAT("2024-01-15T14:30:00Z"), "2024-01-15T14:30:00.000Z")
	eq(t, "datetime_format_custom_date", DATETIME_FORMAT("2024-01-15T14:30:00Z", "YYYY-MM-DD"), "2024-01-15")
	eq(t, "datetime_format_time", DATETIME_FORMAT("2024-01-15T14:30:00Z", "HH:mm"), "14:30")
	eq(t, "datetime_format_12h", DATETIME_FORMAT("2024-01-15T14:30:00Z", "hh:mm A"), "02:30 PM")

	eq(t, "datestr_basic", DATESTR("2024-01-15T14:30:00Z"), "2024-01-15")
	eq(t, "timestr_basic", TIMESTR("2024-01-15T14:30:00Z"), "14:30:00")
	eq(t, "datestr_null", DATESTR(nil), "")

	eq(t, "year_basic", YEAR("2024-01-15T00:00:00Z"), 2024.0)
	eq(t, "month_basic", MONTH("2024-01-15T00:00:00Z"), 1.0)
	eq(t, "day_basic", DAY("2024-01-15T00:00:00Z"), 15.0)
	eq(t, "hour_basic", HOUR("2024-01-15T14:30:00Z"), 14.0)
	eq(t, "minute_basic", MINUTE("2024-01-15T14:30:00Z"), 30.0)
	eq(t, "second_basic", SECOND("2024-01-15T14:30:45Z"), 45.0)

	eq(t, "weekday_sunday", WEEKDAY("2024-01-14T00:00:00Z"), 0.0)
	eq(t, "weekday_monday", WEEKDAY("2024-01-15T00:00:00Z"), 1.0)
	eq(t, "weekday_saturday", WEEKDAY("2024-01-20T00:00:00Z"), 6.0)

	eq(t, "weeknum_basic", WEEKNUM("2024-01-15T00:00:00Z"), 3.0)

	eq(t, "is_same_true", IS_SAME("2024-01-15T00:00:00Z", "2024-01-15T23:59:59Z", "days"), true)
	eq(t, "is_same_false", IS_SAME("2024-01-15T00:00:00Z", "2024-01-16T00:00:00Z", "days"), false)
	eq(t, "is_before_true", IS_BEFORE("2024-01-15T00:00:00Z", "2024-01-16T00:00:00Z", "days"), true)
	eq(t, "is_after_true", IS_AFTER("2024-01-16T00:00:00Z", "2024-01-15T00:00:00Z", "days"), true)

	eq(t, "workday_basic", WORKDAY("2024-01-15T00:00:00Z", 5.0), "2024-01-22T00:00:00.000Z")
	eq(t, "workday_skip_weekend", WORKDAY("2024-01-19T00:00:00Z", 1.0), "2024-01-22T00:00:00.000Z")
	eq(t, "workday_null", WORKDAY(nil, 5.0), nil)

	eq(t, "workday_diff_basic", WORKDAY_DIFF("2024-01-15T00:00:00Z", "2024-01-22T00:00:00Z"), 6.0)
	eq(t, "workday_diff_null", WORKDAY_DIFF(nil, "2024-01-15T00:00:00Z"), 0.0)

	eq(t, "set_timezone_basic", SET_TIMEZONE("2024-01-15T12:00:00Z", "America/New_York"), "2024-01-15T07:00:00.000Z")

	eq(t, "datetime_parse_basic", DATETIME_PARSE("2024-01-15"), "2024-01-15T00:00:00.000Z")
}

// =============================================================================
// Array Functions
// =============================================================================

func TestArray(t *testing.T) {
	eq(t, "arrayjoin_default_separator", ARRAYJOIN(arr("a", "b", "c")), "a, b, c")
	eq(t, "arrayjoin_custom_separator", ARRAYJOIN(arr("a", "b"), "-"), "a-b")
	eq(t, "arrayjoin_non_array", ARRAYJOIN("hello"), "hello")

	eq(t, "arrayunique_basic", ARRAYUNIQUE(arr(1.0, 2.0, 2.0, 3.0)), arr(1.0, 2.0, 3.0))
	eq(t, "arrayunique_preserves_order", ARRAYUNIQUE(arr(3.0, 1.0, 2.0, 1.0, 3.0)), arr(3.0, 1.0, 2.0))

	eq(t, "arraycompact_basic", ARRAYCOMPACT(arr(1.0, nil, "", 2.0)), arr(1.0, 2.0))
	eq(t, "arraycompact_keeps_zero", ARRAYCOMPACT(arr(0.0, nil, false, "")), arr(0.0, false))
	eq(t, "arraycompact_null_input", ARRAYCOMPACT(nil), arr())

	eq(t, "arrayflatten_basic", ARRAYFLATTEN(arr(1.0, arr(2.0, arr(3.0, 4.0)))), arr(1.0, 2.0, 3.0, 4.0))
	eq(t, "arrayflatten_already_flat", ARRAYFLATTEN(arr(1.0, 2.0, 3.0)), arr(1.0, 2.0, 3.0))
	eq(t, "arrayflatten_non_array", ARRAYFLATTEN(5.0), arr(5.0))
}

// =============================================================================
// Regex Functions
// =============================================================================

func TestRegex(t *testing.T) {
	eq(t, "regex_extract_basic", REGEX_EXTRACT("Hello", "[aeiou]"), "e")
	eq(t, "regex_extract_no_match", REGEX_EXTRACT("xyz", "[aeiou]"), nil)
	eq(t, "regex_match_true", REGEX_MATCH("Hello", "^.e"), true)
	eq(t, "regex_match_false", REGEX_MATCH("Hello", "^z"), false)
	eq(t, "regex_replace_basic", REGEX_REPLACE("Hello", "[aeiou]", "*"), "H*ll*")
}

// =============================================================================
// Transpiled equality shape (myairtable-02fg regression)
// =============================================================================

func TestEqualityShape(t *testing.T) {
	if !(N(5.0) == N(5.0)) {
		t.Errorf("numeric eq")
	}
	if !(N(4.0) != N(5.0)) {
		t.Errorf("numeric neq")
	}
	if !(S("hi") == S("hi")) {
		t.Errorf("string eq")
	}
	if !(S(5.0) == S(5.0)) {
		t.Errorf("string coercion eq")
	}
}
