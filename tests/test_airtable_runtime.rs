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
