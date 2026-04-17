use myairtable_static::*;

#[test]
fn creates_client() {
    let _client = AirtableClient::new("test_key", "appTEST123");
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
