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
    assert!(matches!(val, VecOrValue::Multiple(v) if v.len() == 2));
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
