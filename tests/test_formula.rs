use myairtable_static::formula::*;

// =============================================================================
// Combinators
// =============================================================================

#[test]
fn and_combines_formulas() {
    assert_eq!(AND(&["A", "B", "C"]), "AND(A,B,C)");
}

#[test]
fn and_single_returns_bare() {
    assert_eq!(AND(&["A"]), "A");
}

#[test]
fn and_empty_returns_empty() {
    assert_eq!(AND(&[]), "");
}

#[test]
fn and_filters_empty_strings() {
    assert_eq!(AND(&["A", "", "B"]), "AND(A,B)");
}

#[test]
fn or_combines_formulas() {
    assert_eq!(OR(&["A", "B"]), "OR(A,B)");
}

#[test]
fn not_wraps_formula() {
    assert_eq!(NOT("A"), "NOT(A)");
}

#[test]
fn xor_combines_formulas() {
    assert_eq!(XOR(&["A", "B"]), "XOR(A,B)");
}

// =============================================================================
// Record ID
// =============================================================================

#[test]
fn id_equals() {
    assert_eq!(FormulaId.equals("rec123"), "RECORD_ID()='rec123'");
}

#[test]
fn id_in_list_empty() {
    assert_eq!(FormulaId.in_list(&[]), "FALSE()");
}

#[test]
fn id_in_list_single() {
    assert_eq!(FormulaId.in_list(&["rec123"]), "RECORD_ID()='rec123'");
}

#[test]
fn id_in_list_multiple() {
    let result = FormulaId.in_list(&["rec1", "rec2"]);
    assert!(result.starts_with("OR("));
    assert!(result.contains("rec1"));
    assert!(result.contains("rec2"));
}

// =============================================================================
// Text Field — equality
// =============================================================================

#[test]
fn text_equals_case_sensitive() {
    let f = FormulaTextField::new("fld123");
    assert_eq!(f.equals("hello", true, false), "{fld123}=\"hello\"");
}

#[test]
fn text_equals_escapes_quotes() {
    let f = FormulaTextField::new("fld123");
    assert_eq!(
        f.equals("say \"hi\"", true, false),
        "{fld123}=\"say \\\"hi\\\"\""
    );
}

#[test]
fn text_equals_case_insensitive() {
    let f = FormulaTextField::new("fld123");
    let result = f.equals("hello", false, false);
    assert!(result.contains("LOWER("));
}

#[test]
fn text_equals_with_trim() {
    let f = FormulaTextField::new("fld123");
    let result = f.equals("hello", true, true);
    assert!(result.contains("TRIM("));
}

#[test]
fn text_equals_any() {
    let f = FormulaTextField::new("fld123");
    let result = f.equals_any(&["a", "b"], true, false);
    assert!(result.starts_with("OR("));
    assert!(result.contains("{fld123}=\"a\""));
    assert!(result.contains("{fld123}=\"b\""));
}

#[test]
fn text_not_equals() {
    let f = FormulaTextField::new("fld123");
    let result = f.not_equals("hello", true, false);
    assert_eq!(result, "{fld123}!=\"hello\"");
}

// =============================================================================
// Text Field — substring search
// =============================================================================

#[test]
fn text_contains_case_insensitive_trimmed() {
    let f = FormulaTextField::new("fld123");
    let result = f.contains("test", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains("LOWER("));
    assert!(result.contains("TRIM("));
    assert!(result.contains(">0"));
}

#[test]
fn text_contains_case_sensitive() {
    let f = FormulaTextField::new("fld123");
    let result = f.contains("test", true, false);
    assert!(!result.contains("LOWER("));
    assert!(result.contains("FIND("));
}

#[test]
fn text_contains_any() {
    let f = FormulaTextField::new("fld123");
    let result = f.contains_any(&["a", "b"], false, true);
    assert!(result.starts_with("OR("));
}

#[test]
fn text_contains_all() {
    let f = FormulaTextField::new("fld123");
    let result = f.contains_all(&["a", "b"], false, true);
    assert!(result.starts_with("AND("));
}

#[test]
fn text_not_contains() {
    let f = FormulaTextField::new("fld123");
    let result = f.not_contains("test", false, true);
    assert!(result.starts_with("NOT("));
}

// =============================================================================
// Text Field — starts/ends with
// =============================================================================

#[test]
fn text_starts_with() {
    let f = FormulaTextField::new("fld123");
    let result = f.starts_with("hello", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains("=1"));
}

#[test]
fn text_not_starts_with() {
    let f = FormulaTextField::new("fld123");
    let result = f.not_starts_with("hello", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains("!=1"));
}

#[test]
fn text_ends_with() {
    let f = FormulaTextField::new("fld123");
    let result = f.ends_with("world", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains("LEN("));
    assert!(result.contains("+1"));
}

#[test]
fn text_not_ends_with() {
    let f = FormulaTextField::new("fld123");
    let result = f.not_ends_with("world", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains("!=LEN("));
}

// =============================================================================
// Text Field — special
// =============================================================================

#[test]
fn text_phone_equals() {
    let f = FormulaTextField::new("fld123");
    let result = f.phone_equals("+1 (555) 123-4567");
    assert!(result.contains("SUBSTITUTE("));
    assert!(result.contains("15551234567"));
}

#[test]
fn text_regex_match() {
    let f = FormulaTextField::new("fld123");
    assert_eq!(
        f.regex_match("^[A-Z]+$"),
        "REGEX_MATCH({fld123},\"^[A-Z]+$\")"
    );
}

#[test]
fn text_empty() {
    let f = FormulaTextField::new("fld123");
    assert_eq!(f.empty(), "{fld123}=BLANK()");
}

#[test]
fn text_not_empty() {
    let f = FormulaTextField::new("fld123");
    assert_eq!(f.not_empty(), "{fld123}!=BLANK()");
}

// =============================================================================
// Single Select Field
// =============================================================================

#[test]
fn single_select_equals() {
    let f = FormulaSingleSelectField::new("fld123");
    assert_eq!(f.equals("Choice 1", true, false), "{fld123}=\"Choice 1\"");
}

#[test]
fn single_select_equals_any() {
    let f = FormulaSingleSelectField::new("fld123");
    let result = f.equals_any(&["A", "B"], true, false);
    assert!(result.starts_with("OR("));
}

#[test]
fn single_select_not_equals() {
    let f = FormulaSingleSelectField::new("fld123");
    let result = f.not_equals("Choice 1", true, false);
    assert!(result.contains("!=\"Choice 1\""));
}

#[test]
fn single_select_empty() {
    let f = FormulaSingleSelectField::new("fld123");
    assert_eq!(f.empty(), "{fld123}=BLANK()");
}

// =============================================================================
// Multi Select Field
// =============================================================================

#[test]
fn multi_select_contains_option() {
    let f = FormulaMultiSelectField::new("fld123");
    let result = f.contains("Option 1", false, true);
    assert!(result.contains("FIND("));
    assert!(result.contains(">0"));
}

#[test]
fn multi_select_contains_any_options() {
    let f = FormulaMultiSelectField::new("fld123");
    let result = f.contains_any(&["A", "B"], false, true);
    assert!(result.starts_with("OR("));
}

#[test]
fn multi_select_contains_all_options() {
    let f = FormulaMultiSelectField::new("fld123");
    let result = f.contains_all(&["A", "B"], false, true);
    assert!(result.starts_with("AND("));
}

#[test]
fn multi_select_not_contains_option() {
    let f = FormulaMultiSelectField::new("fld123");
    let result = f.not_contains("A", false, true);
    assert!(result.starts_with("NOT("));
}

// =============================================================================
// Number Field
// =============================================================================

#[test]
fn number_equals() {
    assert_eq!(FormulaNumberField::new("fld123").equals(42), "{fld123}=42");
}

#[test]
fn number_not_equals() {
    assert_eq!(
        FormulaNumberField::new("fld123").not_equals(42),
        "{fld123}!=42"
    );
}

#[test]
fn number_greater_than() {
    assert_eq!(
        FormulaNumberField::new("fld123").greater_than(10),
        "{fld123}>10"
    );
}

#[test]
fn number_less_than() {
    assert_eq!(
        FormulaNumberField::new("fld123").less_than(10),
        "{fld123}<10"
    );
}

#[test]
fn number_greater_than_or_equals() {
    assert_eq!(
        FormulaNumberField::new("fld123").greater_than_or_equals(10),
        "{fld123}>=10"
    );
}

#[test]
fn number_less_than_or_equals() {
    assert_eq!(
        FormulaNumberField::new("fld123").less_than_or_equals(10),
        "{fld123}<=10"
    );
}

#[test]
fn number_between_inclusive() {
    assert_eq!(
        FormulaNumberField::new("fld123").between(10, 20, true),
        "AND({fld123}>=10,{fld123}<=20)"
    );
}

#[test]
fn number_between_exclusive() {
    assert_eq!(
        FormulaNumberField::new("fld123").between(10, 20, false),
        "AND({fld123}>10,{fld123}<20)"
    );
}

#[test]
fn number_with_float() {
    assert_eq!(
        FormulaNumberField::new("fld123").equals(3.14),
        "{fld123}=3.14"
    );
}

// =============================================================================
// Boolean Field
// =============================================================================

#[test]
fn boolean_is_true() {
    assert_eq!(
        FormulaBooleanField::new("fld123").is_true(),
        "{fld123}=TRUE()"
    );
}

#[test]
fn boolean_is_false() {
    assert_eq!(
        FormulaBooleanField::new("fld123").is_false(),
        "{fld123}=FALSE()"
    );
}

#[test]
fn boolean_equals_true() {
    assert_eq!(
        FormulaBooleanField::new("fld123").equals(true),
        "{fld123}=TRUE()"
    );
}

#[test]
fn boolean_equals_false() {
    assert_eq!(
        FormulaBooleanField::new("fld123").equals(false),
        "{fld123}=FALSE()"
    );
}

// =============================================================================
// Date Field — absolute dates
// =============================================================================

#[test]
fn date_on() {
    let result = FormulaDateField::new("fld123").on("2025-01-15");
    assert!(result.contains("DATETIME_PARSE('2025-01-15')"));
    assert!(result.contains("=DATETIME_PARSE({fld123})"));
}

#[test]
fn date_not_on() {
    assert!(FormulaDateField::new("fld123")
        .not_on("2025-01-15")
        .contains("!="));
}

#[test]
fn date_after() {
    assert!(FormulaDateField::new("fld123")
        .after("2025-01-15")
        .contains("<DATETIME_PARSE"));
}

#[test]
fn date_before() {
    assert!(FormulaDateField::new("fld123")
        .before("2025-01-15")
        .contains(">DATETIME_PARSE"));
}

#[test]
fn date_on_or_after() {
    assert!(FormulaDateField::new("fld123")
        .on_or_after("2025-01-15")
        .contains("<=DATETIME_PARSE"));
}

#[test]
fn date_on_or_before() {
    assert!(FormulaDateField::new("fld123")
        .on_or_before("2025-01-15")
        .contains(">=DATETIME_PARSE"));
}

#[test]
fn date_between_inclusive() {
    assert!(FormulaDateField::new("fld123")
        .between("2025-01-01", "2025-12-31", true)
        .starts_with("AND("));
}

#[test]
fn date_between_exclusive() {
    assert!(FormulaDateField::new("fld123")
        .between("2025-01-01", "2025-12-31", false)
        .starts_with("AND("));
}

#[test]
fn date_empty() {
    assert_eq!(FormulaDateField::new("fld123").empty(), "{fld123}=BLANK()");
}

#[test]
fn date_not_empty() {
    assert_eq!(
        FormulaDateField::new("fld123").not_empty(),
        "{fld123}!=BLANK()"
    );
}

// =============================================================================
// Date Field — time-ago chaining
// =============================================================================

#[test]
fn date_before_days_ago() {
    let result = FormulaDateField::new("fld123").before_chain().days_ago(7);
    assert!(result.contains("DATETIME_DIFF(NOW(),{fld123},\"days\")"));
    assert!(result.contains(">7"));
}

#[test]
fn date_after_years_ago() {
    let result = FormulaDateField::new("fld123").after_chain().years_ago(1);
    assert!(result.contains("\"years\""));
    assert!(result.contains("<1"));
}

#[test]
fn date_on_chain_days_ago() {
    let result = FormulaDateField::new("fld123").on_chain().days_ago(30);
    assert!(result.contains("=30"));
}

#[test]
fn date_on_or_after_chain_weeks_ago() {
    let result = FormulaDateField::new("fld123")
        .on_or_after_chain()
        .weeks_ago(2);
    assert!(result.contains("\"weeks\""));
    assert!(result.contains("<=2"));
}

#[test]
fn date_hours_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .hours_ago(24)
        .contains("\"hours\""));
}
#[test]
fn date_minutes_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .minutes_ago(60)
        .contains("\"minutes\""));
}
#[test]
fn date_seconds_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .seconds_ago(3600)
        .contains("\"seconds\""));
}
#[test]
fn date_months_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .months_ago(6)
        .contains("\"months\""));
}
#[test]
fn date_quarters_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .quarters_ago(2)
        .contains("\"quarters\""));
}
#[test]
fn date_milliseconds_ago() {
    assert!(FormulaDateField::new("fld123")
        .before_chain()
        .milliseconds_ago(5000)
        .contains("\"milliseconds\""));
}

// =============================================================================
// Attachments Field
// =============================================================================

#[test]
fn attachments_not_empty() {
    assert_eq!(
        FormulaAttachmentsField::new("fld123").not_empty(),
        "LEN({fld123})>0"
    );
}
#[test]
fn attachments_empty() {
    assert_eq!(
        FormulaAttachmentsField::new("fld123").empty(),
        "LEN({fld123})=0"
    );
}
#[test]
fn attachments_count() {
    assert_eq!(
        FormulaAttachmentsField::new("fld123").count(3),
        "LEN({fld123})=3"
    );
}

// =============================================================================
// Lookup Field
// =============================================================================
// FormulaLookupField wraps the field reference in ARRAYJOIN for string ops so
// Airtable can coerce the array to a string. Equality (=) is unaffected because
// Airtable already coerces arrays under =.

#[test]
fn lookup_contains_wraps_in_arrayjoin() {
    let f = FormulaLookupField::new("fldClient");
    let result = f.contains("groundwork", false, true);
    assert!(
        result.contains("ARRAYJOIN({fldClient}"),
        "missing ARRAYJOIN: {result}"
    );
    assert!(result.contains("FIND("), "missing FIND: {result}");
    assert!(result.contains("LOWER("), "missing LOWER: {result}");
}

#[test]
fn lookup_starts_with_wraps_in_arrayjoin() {
    let f = FormulaLookupField::new("fldClient");
    let result = f.starts_with("Ground", false, true);
    assert!(
        result.contains("ARRAYJOIN({fldClient}"),
        "missing ARRAYJOIN: {result}"
    );
}

#[test]
fn lookup_ends_with_wraps_in_arrayjoin() {
    let f = FormulaLookupField::new("fldClient");
    let result = f.ends_with("BioAg", false, true);
    assert!(
        result.contains("ARRAYJOIN({fldClient}"),
        "missing ARRAYJOIN: {result}"
    );
    assert!(result.contains("LEN("), "missing LEN: {result}");
}

#[test]
fn lookup_equals_does_not_wrap_in_arrayjoin() {
    // `=` already coerces arrays to comma-strings — no ARRAYJOIN needed.
    let f = FormulaLookupField::new("fldClient");
    let result = f.equals("Groundwork Bio Ag", true, false);
    assert!(
        !result.contains("ARRAYJOIN"),
        "should not wrap equals: {result}"
    );
    assert!(result.contains("{fldClient}"), "missing field: {result}");
}

#[test]
fn lookup_not_empty_does_not_wrap() {
    let f = FormulaLookupField::new("fldClient");
    assert!(!f.not_empty().contains("ARRAYJOIN"));
}

#[test]
fn text_field_unaffected_regression() {
    // Regression: FormulaTextField must still emit a bare {field} reference.
    let f = FormulaTextField::new("fldName");
    assert!(!f.contains("hello", false, true).contains("ARRAYJOIN"));
}
