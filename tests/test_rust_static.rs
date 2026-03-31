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
