use myairtable_static::*;

#[test]
fn creates_client() {
    let _client = AirtableClient::new("test_key", "appTEST123");
}

#[test]
fn retry_delay_honors_retry_after_and_caps_backoff() {
    // Retry-After path: the (capped) value plus a small bounded jitter of up to value/4.
    // With jitter=0.0 the value is used directly.
    assert_eq!(AirtableClient::retry_delay_secs(Some(5.0), 0, 0.0), 5.0);
    // A huge/broken Retry-After is capped at the 30s max even with jitter=0.0.
    assert_eq!(
        AirtableClient::retry_delay_secs(Some(999999.0), 0, 0.0),
        30.0
    );
    // Retry-After jitter adds up to value/4 on top of the (capped) value.
    let d = AirtableClient::retry_delay_secs(Some(8.0), 0, 0.999);
    assert!(
        (8.0..=10.0).contains(&d),
        "jittered Retry-After {d} out of [8.0, 10.0]"
    );

    // No Retry-After: FULL jitter on exponential backoff -> jitter * min(cap, base * 2^attempt).
    // With jitter=0.0 the delay is 0 (full jitter spans [0, window)).
    assert_eq!(AirtableClient::retry_delay_secs(None, 0, 0.0), 0.0);
    assert_eq!(AirtableClient::retry_delay_secs(None, 2, 0.0), 0.0);
    // With jitter just under 1.0, the delay approaches the backoff window (base * 2^attempt).
    let d0 = AirtableClient::retry_delay_secs(None, 0, 0.999);
    assert!(
        (0.0..=1.0).contains(&d0),
        "attempt 0 jittered delay {d0} out of [0.0, 1.0]"
    );
    let d2 = AirtableClient::retry_delay_secs(None, 2, 0.999);
    assert!(
        (0.0..=4.0).contains(&d2),
        "attempt 2 jittered delay {d2} out of [0.0, 4.0]"
    );
    // The backoff window is capped at the 30s max (1 * 2^10 = 1024 -> 30).
    let dcap = AirtableClient::retry_delay_secs(None, 10, 0.999);
    assert!(
        (0.0..=30.0).contains(&dcap),
        "capped jittered delay {dcap} out of [0.0, 30.0]"
    );
}

#[test]
fn should_retry_429_regardless_of_idempotency() {
    // 429 means the request was rejected and nothing was applied, so it is always safe to retry
    // whether or not the operation is idempotent.
    assert!(AirtableClient::should_retry(429, true, 0));
    assert!(AirtableClient::should_retry(429, false, 0));
}

#[test]
fn should_retry_5xx_only_when_idempotent() {
    // A non-idempotent op (e.g. POST create) may have been partially applied on a 5xx, so it must
    // NOT be retried; an idempotent op is safe to retry.
    for status in [500u16, 502, 503, 599] {
        assert!(
            AirtableClient::should_retry(status, true, 0),
            "idempotent {status} should retry"
        );
        assert!(
            !AirtableClient::should_retry(status, false, 0),
            "non-idempotent {status} must not retry"
        );
    }
}

#[test]
fn should_retry_never_retries_success_or_4xx() {
    // 2xx/3xx and non-429 4xx are terminal regardless of idempotency.
    for status in [200u16, 201, 204, 301, 400, 401, 403, 404, 422] {
        assert!(
            !AirtableClient::should_retry(status, true, 0),
            "idempotent {status} must not retry"
        );
        assert!(
            !AirtableClient::should_retry(status, false, 0),
            "non-idempotent {status} must not retry"
        );
    }
    // 499 is below the 5xx range and must not retry even though 599 (in range) does.
    assert!(!AirtableClient::should_retry(499, true, 0));
}

#[test]
fn should_retry_respects_attempt_cap() {
    // RETRY_MAX_ATTEMPTS is 5: attempts 0..=4 may retry, attempt 5+ must stop, even for a 429.
    assert!(AirtableClient::should_retry(429, false, 4));
    assert!(!AirtableClient::should_retry(429, false, 5));
    assert!(!AirtableClient::should_retry(429, true, 5));
    // The cap also applies to retryable 5xx on idempotent requests.
    assert!(AirtableClient::should_retry(503, true, 4));
    assert!(!AirtableClient::should_retry(503, true, 5));
    assert!(!AirtableClient::should_retry(503, true, 100));
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
