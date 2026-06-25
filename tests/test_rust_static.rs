use myairtable_static::*;

#[test]
fn creates_client() {
    let _client = AirtableClient::new("test_key", "appTEST123");
}

#[test]
fn retry_delay_honors_retry_after_and_caps_backoff() {
    // A 429 Retry-After (seconds) is used directly.
    assert_eq!(AirtableClient::retry_delay_secs(Some(5.0), 0, 0.0), 5.0);
    // No Retry-After: exponential base * 2^attempt.
    assert_eq!(AirtableClient::retry_delay_secs(None, 0, 0.0), 1.0);
    assert_eq!(AirtableClient::retry_delay_secs(None, 2, 0.0), 4.0);
    // Capped at the 30s max (1 * 2^10 = 1024 -> 30).
    assert_eq!(AirtableClient::retry_delay_secs(None, 10, 0.0), 30.0);
    // Decorrelated jitter adds up to delay/4.
    let d = AirtableClient::retry_delay_secs(None, 0, 0.999);
    assert!(
        (1.0..=1.25).contains(&d),
        "jittered delay {d} out of [1.0, 1.25]"
    );
}

#[test]
fn vec_or_value_deserializes_single() {
    let json = r#""hello""#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    assert!(matches!(val, VecOrValue::Single(s) if s == "hello"));
}

#[test]
fn vec_or_value_deserializes_multiple() {
    let json = r#"["a", "b"]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 2);
    assert_eq!(v[0].as_deref(), Some("a"));
    assert_eq!(v[1].as_deref(), Some("b"));
}

#[test]
fn vec_or_value_deserializes_multiple_with_nulls() {
    let json = r#"[null, "a", null, "b"]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 4);
    assert!(v[0].is_none());
    assert_eq!(v[1].as_deref(), Some("a"));
    assert!(v[2].is_none());
    assert_eq!(v[3].as_deref(), Some("b"));
}

#[test]
fn vec_or_value_deserializes_all_nulls() {
    let json = r#"[null, null]"#;
    let val: VecOrValue<i64> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 2);
    assert!(v.iter().all(|x| x.is_none()));
}

#[test]
fn vec_or_value_deserializes_empty() {
    let json = r#"[]"#;
    let val: VecOrValue<String> = serde_json::from_str(json).unwrap();
    assert!(matches!(val, VecOrValue::Multiple(v) if v.is_empty()));
}

#[test]
fn vec_or_value_serializes_multiple_with_nulls() {
    let val: VecOrValue<String> =
        VecOrValue::Multiple(vec![Some("a".into()), None, Some("b".into())]);
    let json = serde_json::to_string(&val).unwrap();
    assert_eq!(json, r#"["a",null,"b"]"#);
}

// =============================================================================
// SpecialNumber / ErrorValue / MaybeSpecialOrError / MaybeError
// =============================================================================

#[test]
fn special_number_deserializes() {
    let v: SpecialNumber = serde_json::from_str(r#"{"specialValue":"NaN"}"#).unwrap();
    assert_eq!(v.special_value, "NaN");
    let v: SpecialNumber = serde_json::from_str(r#"{"specialValue":"Infinity"}"#).unwrap();
    assert_eq!(v.special_value, "Infinity");
}

#[test]
fn error_value_deserializes() {
    let v: ErrorValue = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert_eq!(v.error, "#ERROR!");
}

#[test]
fn maybe_special_or_error_deserializes_value() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str("42").unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Value(n) if n == 42.0));
}

#[test]
fn maybe_special_or_error_deserializes_special() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str(r#"{"specialValue":"NaN"}"#).unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Special(s) if s.special_value == "NaN"));
}

#[test]
fn maybe_special_or_error_deserializes_error() {
    let v: MaybeSpecialOrError<f64> = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert!(matches!(v, MaybeSpecialOrError::Error(e) if e.error == "#ERROR!"));
}

#[test]
fn maybe_error_deserializes_value() {
    let v: MaybeError<String> = serde_json::from_str(r#""hello""#).unwrap();
    assert!(matches!(v, MaybeError::Value(s) if s == "hello"));
}

#[test]
fn maybe_error_deserializes_error() {
    let v: MaybeError<String> = serde_json::from_str(r##"{"error":"#ERROR!"}"##).unwrap();
    assert!(matches!(v, MaybeError::Error(e) if e.error == "#ERROR!"));
}

#[test]
fn maybe_special_or_error_helpers() {
    let v: MaybeSpecialOrError<i64> = 42.into();
    assert!(v.is_value());
    assert_eq!(v.value(), Some(&42));
    assert_eq!(v.clone().into_value(), Some(42));
    assert!(!v.is_special());
    assert!(!v.is_error());

    let e: MaybeSpecialOrError<i64> = MaybeSpecialOrError::Error(ErrorValue {
        error: "#ERROR!".into(),
    });
    assert!(e.is_error());
    assert!(e.value().is_none());
    assert_eq!(e.error().map(|x| x.error.as_str()), Some("#ERROR!"));
}

#[test]
fn maybe_error_helpers() {
    let v: MaybeError<String> = "hi".to_string().into();
    assert!(v.is_value());
    assert_eq!(v.value().map(String::as_str), Some("hi"));
    assert!(!v.is_error());

    let e: MaybeError<String> = MaybeError::Error(ErrorValue {
        error: "#ERROR!".into(),
    });
    assert!(e.is_error());
    assert_eq!(e.error().map(|x| x.error.as_str()), Some("#ERROR!"));
}

#[test]
fn vec_or_value_of_maybe_special_or_error_mixed_array() {
    let json = r##"[1, {"specialValue":"NaN"}, {"error":"#ERROR!"}, null]"##;
    let val: VecOrValue<MaybeSpecialOrError<i64>> = serde_json::from_str(json).unwrap();
    let VecOrValue::Multiple(v) = val else {
        panic!("expected Multiple");
    };
    assert_eq!(v.len(), 4);
    assert!(matches!(v[0], Some(MaybeSpecialOrError::Value(1))));
    assert!(matches!(&v[1], Some(MaybeSpecialOrError::Special(s)) if s.special_value == "NaN"));
    assert!(matches!(&v[2], Some(MaybeSpecialOrError::Error(e)) if e.error == "#ERROR!"));
    assert!(v[3].is_none());
}

// =============================================================================
// URL building
// =============================================================================

#[test]
fn build_url_base_only() {
    assert_eq!(
        build_url("appXXX", "", "", ""),
        "https://airtable.com/appXXX"
    );
}

#[test]
fn build_url_base_and_table() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "", ""),
        "https://airtable.com/appXXX/tblYYY"
    );
}

#[test]
fn build_url_with_view() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "viwZZZ", ""),
        "https://airtable.com/appXXX/tblYYY/viwZZZ"
    );
}

#[test]
fn build_url_with_record() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "", "recAAA"),
        "https://airtable.com/appXXX/tblYYY/recAAA"
    );
}

#[test]
fn build_url_all_params() {
    assert_eq!(
        build_url("appXXX", "tblYYY", "viwZZZ", "recAAA"),
        "https://airtable.com/appXXX/tblYYY/viwZZZ/recAAA"
    );
}

#[test]
fn build_url_empty() {
    assert_eq!(build_url("", "", "", ""), "https://airtable.com");
}
