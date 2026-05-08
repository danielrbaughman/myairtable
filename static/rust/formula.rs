// =============================================================================
// Combinators
// =============================================================================

/// Combine formulas with AND logic.
#[allow(non_snake_case)]
pub fn AND(args: &[&str]) -> String {
    let filtered: Vec<&str> = args.iter().copied().filter(|s| !s.is_empty()).collect();
    match filtered.len() {
        0 => String::new(),
        1 => filtered[0].to_string(),
        _ => format!("AND({})", filtered.join(",")),
    }
}

/// Combine formulas with OR logic.
#[allow(non_snake_case)]
pub fn OR(args: &[&str]) -> String {
    let filtered: Vec<&str> = args.iter().copied().filter(|s| !s.is_empty()).collect();
    match filtered.len() {
        0 => String::new(),
        1 => filtered[0].to_string(),
        _ => format!("OR({})", filtered.join(",")),
    }
}

/// Negate a formula.
#[allow(non_snake_case)]
pub fn NOT(formula: &str) -> String {
    format!("NOT({formula})")
}

/// Exclusive OR.
#[allow(non_snake_case)]
pub fn XOR(args: &[&str]) -> String {
    let filtered: Vec<&str> = args.iter().copied().filter(|s| !s.is_empty()).collect();
    match filtered.len() {
        0 => String::new(),
        1 => filtered[0].to_string(),
        _ => format!("XOR({})", filtered.join(",")),
    }
}

// =============================================================================
// Helpers
// =============================================================================

fn wrap_field(field: &str, case_sensitive: bool, trim: bool) -> String {
    let mut v = field.to_string();
    if trim {
        v = format!("TRIM({v})");
    }
    if !case_sensitive {
        v = format!("LOWER({v})");
    }
    v
}

fn wrap_value_str(value: &str, case_sensitive: bool, trim: bool) -> String {
    let escaped = value.replace('"', "\\\"");
    let mut v = format!("\"{escaped}\"");
    if trim {
        v = format!("TRIM({v})");
    }
    if !case_sensitive {
        v = format!("LOWER({v})");
    }
    v
}

// =============================================================================
// Traits
// =============================================================================

/// Base trait for all formula field types.
/// Provides field reference and empty/not-empty checks.
pub trait FormulaField {
    fn field_id(&self) -> &str;

    fn field(&self) -> String {
        format!("{{{}}}", self.field_id())
    }

    fn empty(&self) -> String {
        format!("{}=BLANK()", self.field())
    }

    fn not_empty(&self) -> String {
        format!("{}!=BLANK()", self.field())
    }
}

/// Text operations: equals, contains, starts_with, ends_with, regex, phone.
pub trait FormulaTextOps: FormulaField {
    /// Field reference used in string operations (FIND/LEN with LOWER/TRIM).
    /// Override in lookup fields to wrap the reference in `ARRAYJOIN(field, ", ")`
    /// so Airtable can coerce the array to a string. Defaults to bare `{field}`.
    fn string_field(&self) -> String {
        self.field()
    }

    /// Exact equality.
    fn equals(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("{f}={v}")
    }

    /// Equals any of the given values.
    fn equals_any(&self, values: &[&str], case_sensitive: bool, trim: bool) -> String {
        let parts: Vec<String> = values
            .iter()
            .map(|v| self.equals(v, case_sensitive, trim))
            .collect();
        let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
        OR(&refs)
    }

    /// Not equal.
    fn not_equals(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("{f}!={v}")
    }

    /// Contains substring.
    fn contains(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.string_field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("FIND({v},{f})>0")
    }

    /// Contains any of the given values.
    fn contains_any(&self, values: &[&str], case_sensitive: bool, trim: bool) -> String {
        let parts: Vec<String> = values
            .iter()
            .map(|v| self.contains(v, case_sensitive, trim))
            .collect();
        let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
        OR(&refs)
    }

    /// Contains all of the given values.
    fn contains_all(&self, values: &[&str], case_sensitive: bool, trim: bool) -> String {
        let parts: Vec<String> = values
            .iter()
            .map(|v| self.contains(v, case_sensitive, trim))
            .collect();
        let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
        AND(&refs)
    }

    /// Does not contain substring.
    fn not_contains(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        NOT(&self.contains(value, case_sensitive, trim))
    }

    /// Starts with the given value.
    fn starts_with(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.string_field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("FIND({v},{f})=1")
    }

    /// Does not start with the given value.
    fn not_starts_with(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.string_field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("FIND({v},{f})!=1")
    }

    /// Ends with the given value.
    fn ends_with(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.string_field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("FIND({v},{f})=LEN({f})-LEN({v})+1")
    }

    /// Does not end with the given value.
    fn not_ends_with(&self, value: &str, case_sensitive: bool, trim: bool) -> String {
        let f = wrap_field(&self.string_field(), case_sensitive, trim);
        let v = wrap_value_str(value, case_sensitive, trim);
        format!("FIND({v},{f})!=LEN({f})-LEN({v})+1")
    }

    /// Phone number equality (normalizes by removing spaces, dashes, parentheses, +, .).
    fn phone_equals(&self, value: &str) -> String {
        let normalized: String = value
            .chars()
            .filter(|c| !matches!(c, ' ' | '-' | '(' | ')' | '+' | '.'))
            .collect();
        let f = self.field();
        let strip = |s: &str| -> String {
            format!("SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({s},\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")")
        };
        format!("{}=\"{normalized}\"", strip(&f))
    }

    /// Regex match.
    fn regex_match(&self, pattern: &str) -> String {
        let escaped = pattern.replace('"', "\\\"");
        format!("REGEX_MATCH({},\"{escaped}\")", self.field())
    }
}

// =============================================================================
// Record ID
// =============================================================================

/// Formula builder for record IDs.
#[derive(Debug, Clone, Copy)]
pub struct FormulaId;

impl FormulaId {
    /// Match a specific record ID.
    pub fn equals(&self, id: &str) -> String {
        format!("RECORD_ID()='{id}'")
    }

    /// Match any of the given record IDs.
    pub fn in_list(&self, ids: &[&str]) -> String {
        match ids.len() {
            0 => "FALSE()".to_string(),
            1 => self.equals(ids[0]),
            _ => {
                let parts: Vec<String> = ids.iter().map(|id| self.equals(id)).collect();
                let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
                OR(&refs)
            }
        }
    }
}

// =============================================================================
// Text Field
// =============================================================================

/// Formula builder for text fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaTextField {
    field_id: &'static str,
}

impl FormulaTextField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }
}

impl FormulaField for FormulaTextField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

impl FormulaTextOps for FormulaTextField {}

// =============================================================================
// Lookup Field
// =============================================================================

/// Formula builder for `multipleLookupValues` / `lookup` fields.
///
/// Lookup field values are arrays. Airtable does not auto-coerce arrays through
/// `LOWER` / `TRIM` / `FIND`, so `contains`, `starts_with` and `ends_with` would
/// silently match nothing. We override `string_field()` to wrap the reference in
/// `ARRAYJOIN(field, ", ")` so string ops see a string.
///
/// Equality (`=`) is unaffected — Airtable coerces array fields to a comma-joined
/// string under `=`, so direct equality already works.
#[derive(Debug, Clone, Copy)]
pub struct FormulaLookupField {
    field_id: &'static str,
}

impl FormulaLookupField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }
}

impl FormulaField for FormulaLookupField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

impl FormulaTextOps for FormulaLookupField {
    fn string_field(&self) -> String {
        format!("ARRAYJOIN({}, \", \")", self.field())
    }
}

// =============================================================================
// Select Fields
// =============================================================================

/// Formula builder for single select fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaSingleSelectField {
    field_id: &'static str,
}

impl FormulaSingleSelectField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }
}

impl FormulaField for FormulaSingleSelectField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

impl FormulaTextOps for FormulaSingleSelectField {}

/// Formula builder for multi-select fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaMultiSelectField {
    field_id: &'static str,
}

impl FormulaMultiSelectField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }
}

impl FormulaField for FormulaMultiSelectField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

impl FormulaTextOps for FormulaMultiSelectField {}

// =============================================================================
// Number Field
// =============================================================================

/// Formula builder for number fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaNumberField {
    field_id: &'static str,
}

impl FormulaNumberField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }

    /// Equal to value.
    pub fn equals(&self, value: impl std::fmt::Display) -> String {
        format!("{}={value}", self.field())
    }

    /// Not equal to value.
    pub fn not_equals(&self, value: impl std::fmt::Display) -> String {
        format!("{}!={value}", self.field())
    }

    /// Greater than value.
    pub fn greater_than(&self, value: impl std::fmt::Display) -> String {
        format!("{}>{value}", self.field())
    }

    /// Less than value.
    pub fn less_than(&self, value: impl std::fmt::Display) -> String {
        format!("{}<{value}", self.field())
    }

    /// Greater than or equal to value.
    pub fn greater_than_or_equals(&self, value: impl std::fmt::Display) -> String {
        format!("{}>={value}", self.field())
    }

    /// Less than or equal to value.
    pub fn less_than_or_equals(&self, value: impl std::fmt::Display) -> String {
        format!("{}<={value}", self.field())
    }

    /// Between min and max (inclusive by default).
    pub fn between(
        &self,
        min: impl std::fmt::Display,
        max: impl std::fmt::Display,
        inclusive: bool,
    ) -> String {
        if inclusive {
            AND(&[
                &self.greater_than_or_equals(min),
                &self.less_than_or_equals(max),
            ])
        } else {
            AND(&[&self.greater_than(min), &self.less_than(max)])
        }
    }
}

impl FormulaField for FormulaNumberField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

// =============================================================================
// Boolean Field
// =============================================================================

/// Formula builder for checkbox/boolean fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaBooleanField {
    field_id: &'static str,
}

impl FormulaBooleanField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }

    /// Equal to boolean value.
    pub fn equals(&self, value: bool) -> String {
        if value {
            self.is_true()
        } else {
            self.is_false()
        }
    }

    /// Field is checked/true.
    pub fn is_true(&self) -> String {
        format!("{}=TRUE()", self.field())
    }

    /// Field is unchecked/false.
    pub fn is_false(&self) -> String {
        format!("{}=FALSE()", self.field())
    }
}

impl FormulaField for FormulaBooleanField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

// =============================================================================
// Date Field
// =============================================================================

/// Either side of a date comparison: a literal date string or another date field.
pub trait DateOperand {
    fn datetime_parse_expr(&self) -> String;
}

impl DateOperand for &str {
    fn datetime_parse_expr(&self) -> String {
        format!("DATETIME_PARSE('{self}')")
    }
}

impl DateOperand for FormulaDateField {
    fn datetime_parse_expr(&self) -> String {
        format!("DATETIME_PARSE({{{}}})", self.field_id)
    }
}

/// Intermediate builder for date "time ago" comparisons.
#[derive(Debug, Clone)]
pub struct FormulaDateComparison {
    field_id: &'static str,
    op: &'static str,
}

impl FormulaDateComparison {
    /// Compare against a literal date string or another date field.
    pub fn date(&self, other: impl DateOperand) -> String {
        format!(
            "{}{}DATETIME_PARSE({{{}}})",
            other.datetime_parse_expr(),
            self.op,
            self.field_id,
        )
    }

    /// N milliseconds ago.
    pub fn milliseconds_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"milliseconds\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N seconds ago.
    pub fn seconds_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"seconds\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N minutes ago.
    pub fn minutes_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"minutes\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N hours ago.
    pub fn hours_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"hours\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N days ago.
    pub fn days_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"days\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N weeks ago.
    pub fn weeks_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"weeks\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N months ago.
    pub fn months_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"months\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N quarters ago.
    pub fn quarters_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"quarters\"){}{n}",
            self.field_id, self.op
        )
    }

    /// N years ago.
    pub fn years_ago(&self, n: i64) -> String {
        format!(
            "DATETIME_DIFF(NOW(),{{{}}},\"years\"){}{n}",
            self.field_id, self.op
        )
    }
}

/// Formula builder for date fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaDateField {
    field_id: &'static str,
}

impl FormulaDateField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }

    fn comparison(&self, op: &'static str) -> FormulaDateComparison {
        FormulaDateComparison {
            field_id: self.field_id,
            op,
        }
    }

    /// Date equals. Pass a date string or another date field, or call `on_chain()` for chaining.
    pub fn on(&self, date: impl DateOperand) -> String {
        self.comparison("=").date(date)
    }

    /// Returns a DateComparison for chaining with time-ago methods.
    pub fn on_chain(&self) -> FormulaDateComparison {
        self.comparison("=")
    }

    /// Date does not equal.
    pub fn not_on(&self, date: impl DateOperand) -> String {
        self.comparison("!=").date(date)
    }

    /// Returns a DateComparison for chaining.
    pub fn not_on_chain(&self) -> FormulaDateComparison {
        self.comparison("!=")
    }

    /// Date is on or after.
    pub fn on_or_after(&self, date: impl DateOperand) -> String {
        self.comparison("<=").date(date)
    }

    /// Returns a DateComparison for chaining.
    pub fn on_or_after_chain(&self) -> FormulaDateComparison {
        self.comparison("<=")
    }

    /// Date is on or before.
    pub fn on_or_before(&self, date: impl DateOperand) -> String {
        self.comparison(">=").date(date)
    }

    /// Returns a DateComparison for chaining.
    pub fn on_or_before_chain(&self) -> FormulaDateComparison {
        self.comparison(">=")
    }

    /// Date is after.
    pub fn after(&self, date: impl DateOperand) -> String {
        self.comparison("<").date(date)
    }

    /// Returns a DateComparison for chaining.
    pub fn after_chain(&self) -> FormulaDateComparison {
        self.comparison("<")
    }

    /// Date is before.
    pub fn before(&self, date: impl DateOperand) -> String {
        self.comparison(">").date(date)
    }

    /// Returns a DateComparison for chaining.
    pub fn before_chain(&self) -> FormulaDateComparison {
        self.comparison(">")
    }

    /// Date is between start and end.
    pub fn between(
        &self,
        start: impl DateOperand,
        end: impl DateOperand,
        inclusive: bool,
    ) -> String {
        if inclusive {
            AND(&[&self.on_or_after(start), &self.on_or_before(end)])
        } else {
            AND(&[&self.after(start), &self.before(end)])
        }
    }
}

impl FormulaField for FormulaDateField {
    fn field_id(&self) -> &str {
        self.field_id
    }
}

// =============================================================================
// Attachments Field
// =============================================================================

/// Formula builder for attachment fields.
#[derive(Debug, Clone, Copy)]
pub struct FormulaAttachmentsField {
    field_id: &'static str,
}

impl FormulaAttachmentsField {
    pub const fn new(field_id: &'static str) -> Self {
        Self { field_id }
    }

    /// Has exactly N attachments.
    pub fn count(&self, n: usize) -> String {
        format!("LEN({})={n}", self.field())
    }
}

impl FormulaField for FormulaAttachmentsField {
    fn field_id(&self) -> &str {
        self.field_id
    }

    /// Has no attachments.
    fn empty(&self) -> String {
        format!("LEN({})=0", self.field())
    }

    /// Has attachments.
    fn not_empty(&self) -> String {
        format!("LEN({})>0", self.field())
    }
}
