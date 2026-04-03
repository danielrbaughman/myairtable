use myairtable_static::airtable_runtime::*;
use serde_json::json;

// =============================================================================
// Type Coercion — N()
// =============================================================================

#[test]
fn n_null() {
    assert_eq!(N(&json!(null)), 0.0);
}
#[test]
fn n_true() {
    assert_eq!(N(&json!(true)), 1.0);
}
#[test]
fn n_false() {
    assert_eq!(N(&json!(false)), 0.0);
}
#[test]
fn n_int() {
    assert_eq!(N(&json!(42)), 42.0);
}
#[test]
fn n_float() {
    assert_eq!(N(&json!(3.14)), 3.14);
}
#[test]
fn n_string_int() {
    assert_eq!(N(&json!("5")), 5.0);
}
#[test]
fn n_string_float() {
    assert_eq!(N(&json!("3.14")), 3.14);
}
#[test]
fn n_string_invalid() {
    assert_eq!(N(&json!("abc")), 0.0);
}
#[test]
fn n_array_first() {
    assert_eq!(N(&json!([5, 10])), 5.0);
}
#[test]
fn n_array_empty() {
    assert_eq!(N(&json!([])), 0.0);
}

// =============================================================================
// Type Coercion — S()
// =============================================================================

#[test]
fn s_null() {
    assert_eq!(S(&json!(null)), "");
}
#[test]
fn s_true() {
    assert_eq!(S(&json!(true)), "1");
}
#[test]
fn s_false() {
    assert_eq!(S(&json!(false)), "0");
}
#[test]
fn s_whole_float() {
    assert_eq!(S(&json!(15.0)), "15");
} // strips .0
#[test]
fn s_fractional_float() {
    assert_eq!(S(&json!(2.5)), "2.5");
}
#[test]
fn s_int() {
    assert_eq!(S(&json!(42)), "42");
}
#[test]
fn s_string() {
    assert_eq!(S(&json!("hello")), "hello");
}
#[test]
fn s_array_first() {
    assert_eq!(S(&json!(["hello", "world"])), "hello");
}

// =============================================================================
// Type Coercion — A() / AN()
// =============================================================================

#[test]
fn a_flattens_one_level() {
    let result = A(&[json!(1), json!([2, 3]), json!(4)]);
    assert_eq!(result, vec![json!(1), json!(2), json!(3), json!(4)]);
}

#[test]
fn an_coerces_to_numbers() {
    let result = AN(&[json!(1), json!("5"), json!(null)]);
    assert_eq!(result, vec![1.0, 5.0, 0.0]);
}

// =============================================================================
// Math Functions
// =============================================================================

#[test]
fn sum_basic() {
    assert_eq!(SUM(&[json!(1), json!(2), json!(3)]), json!(6));
}
#[test]
fn sum_with_strings() {
    assert_eq!(SUM(&[json!(1), json!("5")]), json!(6));
}

#[test]
fn average_basic() {
    assert_eq!(AVERAGE(&[json!(10), json!(20), json!(30)]), json!(20));
}
#[test]
fn average_empty() {
    assert_eq!(AVERAGE(&[]), json!(null));
}

#[test]
fn count_numbers_only() {
    assert_eq!(
        COUNT(&[json!(1), json!("a"), json!(3), json!(null)]),
        json!(2)
    );
}
#[test]
fn count_bools_not_counted() {
    assert_eq!(COUNT(&[json!(true), json!(false)]), json!(0));
}

#[test]
fn counta_excludes_null_and_empty() {
    assert_eq!(
        COUNTA(&[json!(1), json!(""), json!(null), json!("hi")]),
        json!(2)
    );
}
#[test]
fn counta_counts_bools() {
    assert_eq!(COUNTA(&[json!(true), json!(false)]), json!(2));
}

#[test]
fn min_basic() {
    assert_eq!(MIN(&[json!(5), json!(2), json!(8)]), json!(2));
}
#[test]
fn max_basic() {
    assert_eq!(MAX(&[json!(5), json!(2), json!(8)]), json!(8));
}

#[test]
fn round_basic() {
    assert_eq!(ROUND(&json!(3.456), &json!(2)), json!(3.46));
}
#[test]
fn round_zero() {
    assert_eq!(ROUND(&json!(3.5), &json!(0)), json!(4));
}

#[test]
fn roundup_basic() {
    assert_eq!(ROUNDUP(&json!(3.14), &json!(1)), json!(3.2));
}
#[test]
fn rounddown_basic() {
    assert_eq!(ROUNDDOWN(&json!(3.19), &json!(1)), json!(3.1));
}

#[test]
fn ceiling_basic() {
    assert_eq!(CEILING(&json!(4.3), &json!(2)), json!(6));
}
#[test]
fn ceiling_default() {
    assert_eq!(CEILING(&json!(4.3), &json!(0)), json!(5));
}

#[test]
fn floor_basic() {
    assert_eq!(FLOOR(&json!(4.9), &json!(2)), json!(4));
}

#[test]
fn log_base10() {
    assert_eq!(LOG(&json!(100), None), json!(2));
}
#[test]
fn log_base2() {
    assert_eq!(LOG(&json!(8), Some(&json!(2))), json!(3));
}

#[test]
fn even_positive() {
    assert_eq!(EVEN(&json!(3)), json!(4));
}
#[test]
fn even_already_even() {
    assert_eq!(EVEN(&json!(4)), json!(4));
}
#[test]
fn even_negative() {
    assert_eq!(EVEN(&json!(-3)), json!(-4));
}

#[test]
fn odd_positive() {
    assert_eq!(ODD(&json!(4)), json!(5));
}
#[test]
fn odd_already_odd() {
    assert_eq!(ODD(&json!(3)), json!(3));
}
#[test]
fn odd_negative() {
    assert_eq!(ODD(&json!(-4)), json!(-5));
}

#[test]
fn value_string_number() {
    assert_eq!(VALUE(&json!("42")), json!(42));
}
#[test]
fn value_string_float() {
    assert_eq!(VALUE(&json!("3.14")), json!(3.14));
}
#[test]
fn value_invalid() {
    assert_eq!(VALUE(&json!("abc")), json!(null));
}
#[test]
fn value_null() {
    assert_eq!(VALUE(&json!(null)), json!(0));
}

#[test]
fn power_basic() {
    assert_eq!(POWER(&json!(2), &json!(3)), json!(8));
}
#[test]
fn mod_basic() {
    assert_eq!(MOD(&json!(10), &json!(3)), json!(1));
}
#[test]
fn abs_negative() {
    assert_eq!(ABS(&json!(-5)), json!(5));
}
#[test]
fn sqrt_basic() {
    assert_eq!(SQRT(&json!(9)), json!(3));
}
#[test]
fn int_truncates() {
    assert_eq!(INT(&json!(3.9)), json!(3));
}
#[test]
fn int_negative() {
    assert_eq!(INT(&json!(-3.9)), json!(-3));
}

// =============================================================================
// Logic Functions
// =============================================================================

#[test]
fn if_true() {
    assert_eq!(IF(&json!(true), &json!("yes"), &json!("no")), json!("yes"));
}
#[test]
fn if_false() {
    assert_eq!(IF(&json!(false), &json!("yes"), &json!("no")), json!("no"));
}
#[test]
fn if_null_is_falsy() {
    assert_eq!(IF(&json!(null), &json!("yes"), &json!("no")), json!("no"));
}
#[test]
fn if_zero_is_falsy() {
    assert_eq!(IF(&json!(0), &json!("yes"), &json!("no")), json!("no"));
}
#[test]
fn if_number_is_truthy() {
    assert_eq!(IF(&json!(1), &json!("yes"), &json!("no")), json!("yes"));
}
#[test]
fn if_empty_string_is_falsy() {
    assert_eq!(IF(&json!(""), &json!("yes"), &json!("no")), json!("no"));
}

#[test]
fn switch_match() {
    let cases = vec![(json!(1), json!("one")), (json!(2), json!("two"))];
    assert_eq!(SWITCH(&json!(2), &cases, None), json!("two"));
}
#[test]
fn switch_default() {
    let cases = vec![(json!(1), json!("one"))];
    assert_eq!(
        SWITCH(&json!(99), &cases, Some(&json!("other"))),
        json!("other")
    );
}
#[test]
fn switch_no_match_no_default() {
    let cases = vec![(json!(1), json!("one"))];
    assert_eq!(SWITCH(&json!(99), &cases, None), json!(null));
}

#[test]
fn blank_is_null() {
    assert_eq!(BLANK(), json!(null));
}
#[test]
fn true_is_bool() {
    assert_eq!(TRUE(), json!(true));
}
#[test]
fn false_is_bool() {
    assert_eq!(FALSE(), json!(false));
}

#[test]
fn iserror_null() {
    assert_eq!(ISERROR(&json!(null)), json!(true));
}
#[test]
fn iserror_number() {
    assert_eq!(ISERROR(&json!(5)), json!(false));
}

#[test]
fn is_truthy_tests() {
    assert!(!is_truthy(&json!(null)));
    assert!(!is_truthy(&json!(false)));
    assert!(!is_truthy(&json!(0)));
    assert!(!is_truthy(&json!("")));
    assert!(is_truthy(&json!(true)));
    assert!(is_truthy(&json!(1)));
    assert!(is_truthy(&json!("hello")));
    assert!(is_truthy(&json!([1])));
}

// =============================================================================
// String Functions
// =============================================================================

#[test]
fn left_basic() {
    assert_eq!(LEFT(&json!("hello"), &json!(3)), json!("hel"));
}
#[test]
fn left_zero() {
    assert_eq!(LEFT(&json!("hello"), &json!(0)), json!(""));
}
#[test]
fn left_exceeds() {
    assert_eq!(LEFT(&json!("hi"), &json!(5)), json!("hi"));
}

#[test]
fn right_basic() {
    assert_eq!(RIGHT(&json!("hello"), &json!(3)), json!("llo"));
}
#[test]
fn right_exceeds() {
    assert_eq!(RIGHT(&json!("hi"), &json!(5)), json!("hi"));
}

#[test]
fn mid_basic() {
    assert_eq!(MID(&json!("hello"), &json!(2), &json!(3)), json!("ell"));
}
#[test]
fn mid_start_one() {
    assert_eq!(MID(&json!("hello"), &json!(1), &json!(2)), json!("he"));
}

#[test]
fn find_basic() {
    assert_eq!(FIND(&json!("ll"), &json!("hello"), None), json!(3));
}
#[test]
fn find_not_found() {
    assert_eq!(FIND(&json!("xyz"), &json!("hello"), None), json!(0));
}
#[test]
fn find_case_sensitive() {
    assert_eq!(FIND(&json!("LL"), &json!("hello"), None), json!(0));
}
#[test]
fn find_with_start() {
    assert_eq!(
        FIND(&json!("l"), &json!("hello"), Some(&json!(4))),
        json!(4)
    );
}

#[test]
fn search_case_insensitive() {
    assert_eq!(SEARCH(&json!("LL"), &json!("hello"), None), json!(3));
}
#[test]
fn search_with_start() {
    assert_eq!(
        SEARCH(&json!("l"), &json!("hello"), Some(&json!(4))),
        json!(4)
    );
}

#[test]
fn substitute_all() {
    assert_eq!(
        SUBSTITUTE(&json!("aaa"), &json!("a"), &json!("b"), None),
        json!("bbb")
    );
}
#[test]
fn substitute_nth() {
    assert_eq!(
        SUBSTITUTE(&json!("aaa"), &json!("a"), &json!("b"), Some(&json!(2))),
        json!("aba")
    );
}
#[test]
fn substitute_empty_old() {
    assert_eq!(
        SUBSTITUTE(&json!("hello"), &json!(""), &json!("x"), None),
        json!("hello")
    );
}

#[test]
fn replace_basic() {
    assert_eq!(
        REPLACE(&json!("hello"), &json!(2), &json!(3), &json!("XY")),
        json!("hXYo")
    );
}

#[test]
fn t_string() {
    assert_eq!(T(&json!("hello")), json!("hello"));
}
#[test]
fn t_number() {
    assert_eq!(T(&json!(42)), json!(""));
}
#[test]
fn t_null() {
    assert_eq!(T(&json!(null)), json!(""));
}

#[test]
fn lower_basic() {
    assert_eq!(LOWER(&json!("Hello")), json!("hello"));
}
#[test]
fn upper_basic() {
    assert_eq!(UPPER(&json!("hello")), json!("HELLO"));
}

#[test]
fn trim_basic() {
    assert_eq!(TRIM(&json!("  hello  ")), json!("hello"));
}
#[test]
fn trim_no_extra() {
    assert_eq!(TRIM(&json!("hello")), json!("hello"));
}

#[test]
fn len_basic() {
    assert_eq!(LEN(&json!("hello")), json!(5));
}
#[test]
fn len_empty() {
    assert_eq!(LEN(&json!("")), json!(0));
}

#[test]
fn rept_basic() {
    assert_eq!(REPT(&json!("ab"), &json!(3)), json!("ababab"));
}
#[test]
fn rept_zero() {
    assert_eq!(REPT(&json!("ab"), &json!(0)), json!(""));
}

#[test]
fn concatenate_basic() {
    assert_eq!(
        CONCATENATE(&[json!("a"), json!("b"), json!("c")]),
        json!("abc")
    );
}
#[test]
fn concatenate_with_numbers() {
    assert_eq!(
        CONCATENATE(&[json!("count: "), json!(5)]),
        json!("count: 5")
    );
}

#[test]
fn encode_url_component_basic() {
    assert_eq!(
        ENCODE_URL_COMPONENT(&json!("hello world")),
        json!("hello%20world")
    );
}
#[test]
fn encode_url_component_special() {
    assert_eq!(ENCODE_URL_COMPONENT(&json!("a&b=c")), json!("a%26b%3Dc"));
}

// =============================================================================
// Date/Time Functions
// =============================================================================

#[test]
fn d_iso_string() {
    let dt = D(&json!("2024-01-15T12:00:00Z"));
    assert!(dt.is_some());
    assert_eq!(dt.unwrap().to_rfc3339(), "2024-01-15T12:00:00+00:00");
}

#[test]
fn d_date_only() {
    let dt = D(&json!("2024-01-15"));
    assert!(dt.is_some());
    assert_eq!(dt.unwrap().to_rfc3339(), "2024-01-15T00:00:00+00:00");
}

#[test]
fn d_timestamp() {
    let dt = D(&json!(1705312800));
    assert!(dt.is_some());
}

#[test]
fn d_null() {
    assert!(D(&json!(null)).is_none());
}

#[test]
fn d_empty_string() {
    assert!(D(&json!("")).is_none());
}

#[test]
fn dateadd_days() {
    assert_eq!(
        DATEADD(&json!("2024-01-15T00:00:00Z"), &json!(5), &json!("days")),
        json!("2024-01-20T00:00:00.000Z")
    );
}

#[test]
fn dateadd_months_clamp() {
    // Jan 31 + 1 month = Feb 29 (2024 is leap year)
    assert_eq!(
        DATEADD(&json!("2024-01-31T00:00:00Z"), &json!(1), &json!("months")),
        json!("2024-02-29T00:00:00.000Z")
    );
}

#[test]
fn dateadd_years() {
    assert_eq!(
        DATEADD(&json!("2024-01-15T00:00:00Z"), &json!(1), &json!("years")),
        json!("2025-01-15T00:00:00.000Z")
    );
}

#[test]
fn dateadd_hours() {
    assert_eq!(
        DATEADD(&json!("2024-01-15T12:00:00Z"), &json!(3), &json!("hours")),
        json!("2024-01-15T15:00:00.000Z")
    );
}

#[test]
fn dateadd_null() {
    assert_eq!(
        DATEADD(&json!(null), &json!(5), &json!("days")),
        json!(null)
    );
}

#[test]
fn datetime_diff_days() {
    assert_eq!(
        DATETIME_DIFF(
            &json!("2024-01-20T00:00:00Z"),
            &json!("2024-01-15T00:00:00Z"),
            Some(&json!("days"))
        ),
        json!(5)
    );
}

#[test]
fn datetime_diff_hours() {
    assert_eq!(
        DATETIME_DIFF(
            &json!("2024-01-15T15:00:00Z"),
            &json!("2024-01-15T12:00:00Z"),
            Some(&json!("hours"))
        ),
        json!(3)
    );
}

#[test]
fn datetime_diff_months() {
    assert_eq!(
        DATETIME_DIFF(
            &json!("2024-03-15T00:00:00Z"),
            &json!("2024-01-15T00:00:00Z"),
            Some(&json!("months"))
        ),
        json!(2)
    );
}

#[test]
fn datetime_diff_default_days() {
    assert_eq!(
        DATETIME_DIFF(
            &json!("2024-01-20T00:00:00Z"),
            &json!("2024-01-15T00:00:00Z"),
            None
        ),
        json!(5)
    );
}

#[test]
fn datetime_diff_null() {
    assert_eq!(
        DATETIME_DIFF(
            &json!(null),
            &json!("2024-01-15T00:00:00Z"),
            Some(&json!("days"))
        ),
        json!(0)
    );
}

#[test]
fn datetime_format_default() {
    let result = DATETIME_FORMAT(&json!("2024-01-15T14:30:00Z"), None);
    assert_eq!(result, json!("2024-01-15T14:30:00.000Z"));
}

#[test]
fn datetime_format_custom_date() {
    assert_eq!(
        DATETIME_FORMAT(&json!("2024-01-15T14:30:00Z"), Some(&json!("YYYY-MM-DD"))),
        json!("2024-01-15")
    );
}

#[test]
fn datetime_format_time() {
    assert_eq!(
        DATETIME_FORMAT(&json!("2024-01-15T14:30:00Z"), Some(&json!("HH:mm"))),
        json!("14:30")
    );
}

#[test]
fn datetime_format_12h() {
    assert_eq!(
        DATETIME_FORMAT(&json!("2024-01-15T14:30:00Z"), Some(&json!("hh:mm A"))),
        json!("02:30 PM")
    );
}

#[test]
fn datestr_basic() {
    assert_eq!(DATESTR(&json!("2024-01-15T14:30:00Z")), json!("2024-01-15"));
}

#[test]
fn timestr_basic() {
    assert_eq!(TIMESTR(&json!("2024-01-15T14:30:00Z")), json!("14:30:00"));
}

#[test]
fn datestr_null() {
    assert_eq!(DATESTR(&json!(null)), json!(""));
}

#[test]
fn year_basic() {
    assert_eq!(YEAR(&json!("2024-01-15T00:00:00Z")), json!(2024));
}

#[test]
fn month_basic() {
    assert_eq!(MONTH(&json!("2024-01-15T00:00:00Z")), json!(1));
}

#[test]
fn day_basic() {
    assert_eq!(DAY(&json!("2024-01-15T00:00:00Z")), json!(15));
}

#[test]
fn hour_basic() {
    assert_eq!(HOUR(&json!("2024-01-15T14:30:00Z")), json!(14));
}

#[test]
fn minute_basic() {
    assert_eq!(MINUTE(&json!("2024-01-15T14:30:00Z")), json!(30));
}

#[test]
fn second_basic() {
    assert_eq!(SECOND(&json!("2024-01-15T14:30:45Z")), json!(45));
}

#[test]
fn weekday_sunday() {
    // 2024-01-14 is a Sunday
    assert_eq!(WEEKDAY(&json!("2024-01-14T00:00:00Z")), json!(0));
}

#[test]
fn weekday_monday() {
    // 2024-01-15 is a Monday
    assert_eq!(WEEKDAY(&json!("2024-01-15T00:00:00Z")), json!(1));
}

#[test]
fn weekday_saturday() {
    // 2024-01-20 is a Saturday
    assert_eq!(WEEKDAY(&json!("2024-01-20T00:00:00Z")), json!(6));
}

#[test]
fn weeknum_basic() {
    let result = WEEKNUM(&json!("2024-01-15T00:00:00Z"), None);
    // Jan 15 2024 is in week 3 (Sunday start)
    assert_eq!(result, json!(3));
}

#[test]
fn is_same_true() {
    assert_eq!(
        IS_SAME(
            &json!("2024-01-15T00:00:00Z"),
            &json!("2024-01-15T23:59:59Z"),
            Some(&json!("days"))
        ),
        json!(true)
    );
}

#[test]
fn is_same_false() {
    assert_eq!(
        IS_SAME(
            &json!("2024-01-15T00:00:00Z"),
            &json!("2024-01-16T00:00:00Z"),
            Some(&json!("days"))
        ),
        json!(false)
    );
}

#[test]
fn is_before_true() {
    assert_eq!(
        IS_BEFORE(
            &json!("2024-01-15T00:00:00Z"),
            &json!("2024-01-16T00:00:00Z"),
            Some(&json!("days"))
        ),
        json!(true)
    );
}

#[test]
fn is_after_true() {
    assert_eq!(
        IS_AFTER(
            &json!("2024-01-16T00:00:00Z"),
            &json!("2024-01-15T00:00:00Z"),
            Some(&json!("days"))
        ),
        json!(true)
    );
}

#[test]
fn workday_basic() {
    // Mon Jan 15 + 5 workdays = Mon Jan 22
    assert_eq!(
        WORKDAY(&json!("2024-01-15T00:00:00Z"), &json!(5)),
        json!("2024-01-22T00:00:00.000Z")
    );
}

#[test]
fn workday_skip_weekend() {
    // Fri Jan 19 + 1 workday = Mon Jan 22
    assert_eq!(
        WORKDAY(&json!("2024-01-19T00:00:00Z"), &json!(1)),
        json!("2024-01-22T00:00:00.000Z")
    );
}

#[test]
fn workday_null() {
    assert_eq!(WORKDAY(&json!(null), &json!(5)), json!(null));
}

#[test]
fn workday_diff_basic() {
    // Mon Jan 15 to Mon Jan 22 = 5 workdays
    assert_eq!(
        WORKDAY_DIFF(
            &json!("2024-01-15T00:00:00Z"),
            &json!("2024-01-22T00:00:00Z")
        ),
        json!(5)
    );
}

#[test]
fn workday_diff_null() {
    assert_eq!(
        WORKDAY_DIFF(&json!(null), &json!("2024-01-15T00:00:00Z")),
        json!(0)
    );
}

#[test]
fn set_timezone_basic() {
    // UTC 12:00 → America/New_York (UTC-5 in January) = 07:00
    let result = SET_TIMEZONE(&json!("2024-01-15T12:00:00Z"), &json!("America/New_York"));
    assert_eq!(result, json!("2024-01-15T07:00:00.000Z"));
}
