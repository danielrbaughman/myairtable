/// AirtableRuntime: Implements Airtable formula functions and operators in Rust.
///
/// All operators route through this module for correct Airtable semantics:
/// - BLANK() is None (treated as 0 in numeric context, "" in string context)
/// - Division by zero returns NaN (Airtable shows #ERROR!)
/// - Type coercion follows Airtable rules, not Rust rules
use chrono::{DateTime, Datelike, Duration, NaiveDate, NaiveDateTime, Timelike, Utc, Weekday};
use chrono_tz::Tz;
use regex::Regex;
use serde_json::Value;

// =============================================================================
// Type Coercion
// =============================================================================

/// Coerce a value to f64. null→0, bool→0/1, string→parse or 0, array→first element.
#[allow(non_snake_case)]
pub fn N(v: &Value) -> f64 {
    match v {
        Value::Null => 0.0,
        Value::Bool(b) => {
            if *b {
                1.0
            } else {
                0.0
            }
        }
        Value::Number(n) => n.as_f64().unwrap_or(0.0),
        Value::String(s) => s.parse::<f64>().unwrap_or(0.0),
        Value::Array(arr) => {
            if let Some(first) = arr.first() {
                N(first)
            } else {
                0.0
            }
        }
        _ => 0.0,
    }
}

/// Coerce a value to String. null→"", bool→"0"/"1", float strips .0 for whole numbers.
#[allow(non_snake_case)]
pub fn S(v: &Value) -> String {
    match v {
        Value::Null => String::new(),
        Value::Bool(b) => {
            if *b {
                "1".to_string()
            } else {
                "0".to_string()
            }
        }
        Value::Number(n) => {
            let f = n.as_f64().unwrap_or(0.0);
            if f.is_nan() {
                "NaN".to_string()
            } else if f.is_infinite() {
                if f > 0.0 {
                    "Infinity".to_string()
                } else {
                    "-Infinity".to_string()
                }
            } else if f == f.trunc() && f.is_finite() {
                format!("{}", f as i64)
            } else {
                format!("{}", f)
            }
        }
        Value::String(s) => s.clone(),
        Value::Array(arr) => {
            if let Some(first) = arr.first() {
                S(first)
            } else {
                String::new()
            }
        }
        _ => String::new(),
    }
}

/// Flatten one level of arrays.
#[allow(non_snake_case)]
pub fn A(args: &[Value]) -> Vec<Value> {
    let mut result = Vec::new();
    for v in args {
        if let Value::Array(arr) = v {
            result.extend(arr.iter().cloned());
        } else {
            result.push(v.clone());
        }
    }
    result
}

/// Flatten one level, then coerce each to f64.
#[allow(non_snake_case)]
pub fn AN(args: &[Value]) -> Vec<f64> {
    A(args).iter().map(|v| N(v)).collect()
}

/// Flatten one level, then coerce each to String.
#[allow(non_snake_case)]
pub fn AS(args: &[Value]) -> Vec<String> {
    A(args).iter().map(|v| S(v)).collect()
}

fn to_value(f: f64) -> Value {
    if f.is_nan() || f.is_infinite() {
        Value::Null
    } else if f == f.trunc() && f.abs() < (i64::MAX as f64) {
        serde_json::json!(f as i64)
    } else {
        serde_json::Number::from_f64(f)
            .map(Value::Number)
            .unwrap_or(Value::Null)
    }
}

// =============================================================================
// Math Functions
// =============================================================================

/// Sum of all values.
#[allow(non_snake_case)]
pub fn SUM(args: &[Value]) -> Value {
    to_value(AN(args).iter().sum())
}

/// Average of all values.
#[allow(non_snake_case)]
pub fn AVERAGE(args: &[Value]) -> Value {
    let nums = AN(args);
    if nums.is_empty() {
        return Value::Null; // NaN
    }
    to_value(nums.iter().sum::<f64>() / nums.len() as f64)
}

/// Count of numeric, non-NaN values.
#[allow(non_snake_case)]
pub fn COUNT(args: &[Value]) -> Value {
    let flat = A(args);
    let count = flat
        .iter()
        .filter(|v| matches!(v, Value::Number(_)) && !N(v).is_nan())
        .count();
    serde_json::json!(count)
}

/// Count of non-null, non-empty-string values.
#[allow(non_snake_case)]
pub fn COUNTA(args: &[Value]) -> Value {
    let flat = A(args);
    let count = flat
        .iter()
        .filter(|v| !v.is_null() && *v != &Value::String(String::new()))
        .count();
    serde_json::json!(count)
}

/// Minimum value.
#[allow(non_snake_case)]
pub fn MIN(args: &[Value]) -> Value {
    let nums = AN(args);
    to_value(nums.iter().copied().fold(f64::INFINITY, f64::min))
}

/// Maximum value.
#[allow(non_snake_case)]
pub fn MAX(args: &[Value]) -> Value {
    let nums = AN(args);
    to_value(nums.iter().copied().fold(f64::NEG_INFINITY, f64::max))
}

/// Round to precision decimal places.
#[allow(non_snake_case)]
pub fn ROUND(v: &Value, precision: &Value) -> Value {
    let n = N(v);
    let p = N(precision) as i32;
    let factor = 10f64.powi(p);
    to_value((n * factor).round() / factor)
}

/// Round up (away from zero) to precision decimal places.
#[allow(non_snake_case)]
pub fn ROUNDUP(v: &Value, precision: &Value) -> Value {
    let n = N(v);
    let p = N(precision) as i32;
    let factor = 10f64.powi(p);
    to_value((n * factor).ceil() / factor)
}

/// Round down (toward zero) to precision decimal places.
#[allow(non_snake_case)]
pub fn ROUNDDOWN(v: &Value, precision: &Value) -> Value {
    let n = N(v);
    let p = N(precision) as i32;
    let factor = 10f64.powi(p);
    to_value((n * factor).floor() / factor)
}

/// Round up to nearest multiple of significance.
#[allow(non_snake_case)]
pub fn CEILING(v: &Value, significance: &Value) -> Value {
    let n = N(v);
    let s = {
        let sig = N(significance);
        if sig == 0.0 {
            1.0
        } else {
            sig
        }
    };
    to_value((n / s).ceil() * s)
}

/// Round down to nearest multiple of significance.
#[allow(non_snake_case)]
pub fn FLOOR(v: &Value, significance: &Value) -> Value {
    let n = N(v);
    let s = {
        let sig = N(significance);
        if sig == 0.0 {
            1.0
        } else {
            sig
        }
    };
    to_value((n / s).floor() * s)
}

/// Logarithm. Default base 10.
#[allow(non_snake_case)]
pub fn LOG(v: &Value, base: Option<&Value>) -> Value {
    let n = N(v);
    let b = base.map(|b| N(b)).unwrap_or(10.0);
    to_value(n.ln() / b.ln())
}

/// Round up to nearest even integer.
#[allow(non_snake_case)]
pub fn EVEN(v: &Value) -> Value {
    let n = N(v);
    let sign = if n < 0.0 { -1.0 } else { 1.0 };
    let abs_ceil = n.abs().ceil() as i64;
    let result = if abs_ceil % 2 == 0 {
        abs_ceil
    } else {
        abs_ceil + 1
    };
    to_value(sign * result as f64)
}

/// Round up to nearest odd integer.
#[allow(non_snake_case)]
pub fn ODD(v: &Value) -> Value {
    let n = N(v);
    let sign = if n < 0.0 { -1.0 } else { 1.0 };
    let abs_ceil = n.abs().ceil() as i64;
    let result = if abs_ceil % 2 == 1 {
        abs_ceil
    } else {
        abs_ceil + 1
    };
    to_value(sign * result as f64)
}

/// Parse string to number. Invalid → null (NaN).
#[allow(non_snake_case)]
pub fn VALUE(v: &Value) -> Value {
    match v {
        Value::Null => to_value(0.0),
        Value::Number(_) => v.clone(),
        Value::String(s) => {
            match s.parse::<f64>() {
                Ok(n) => to_value(n),
                Err(_) => Value::Null, // NaN
            }
        }
        _ => Value::Null,
    }
}

/// Power.
#[allow(non_snake_case)]
pub fn POWER(base: &Value, exp: &Value) -> Value {
    to_value(N(base).powf(N(exp)))
}

/// Modulo.
#[allow(non_snake_case)]
pub fn MOD(v: &Value, divisor: &Value) -> Value {
    to_value(N(v) % N(divisor))
}

/// Absolute value.
#[allow(non_snake_case)]
pub fn ABS(v: &Value) -> Value {
    to_value(N(v).abs())
}

/// Euler's number raised to a power.
#[allow(non_snake_case)]
pub fn EXP(v: &Value) -> Value {
    to_value(N(v).exp())
}

/// Square root.
#[allow(non_snake_case)]
pub fn SQRT(v: &Value) -> Value {
    to_value(N(v).sqrt())
}

/// Truncate to integer.
#[allow(non_snake_case)]
pub fn INT(v: &Value) -> Value {
    to_value(N(v).trunc())
}

// =============================================================================
// Logic Functions
// =============================================================================

/// Conditional: if condition is truthy, return if_true, else if_false.
#[allow(non_snake_case)]
pub fn IF(condition: &Value, if_true: &Value, if_false: &Value) -> Value {
    if is_truthy(condition) {
        if_true.clone()
    } else {
        if_false.clone()
    }
}

/// Switch/case expression.
#[allow(non_snake_case)]
pub fn SWITCH(expr: &Value, cases: &[(Value, Value)], default: Option<&Value>) -> Value {
    for (pattern, result) in cases {
        if expr == pattern {
            return result.clone();
        }
    }
    default.cloned().unwrap_or(Value::Null)
}

/// Return null (BLANK).
#[allow(non_snake_case)]
pub fn BLANK() -> Value {
    Value::Null
}

/// Return an error marker (null, since JSON can't represent errors).
#[allow(non_snake_case)]
pub fn ERROR(_message: Option<&Value>) -> Value {
    Value::Null
}

/// Check if value is an error (NaN or null from error context).
#[allow(non_snake_case)]
pub fn ISERROR(v: &Value) -> Value {
    Value::Bool(v.is_null())
}

/// Return true.
#[allow(non_snake_case)]
pub fn TRUE() -> Value {
    Value::Bool(true)
}

/// Return false.
#[allow(non_snake_case)]
pub fn FALSE() -> Value {
    Value::Bool(false)
}

/// Check if a value is truthy (non-null, non-false, non-zero, non-empty-string).
pub fn is_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
        Value::String(s) => !s.is_empty(),
        Value::Array(arr) => !arr.is_empty(),
        Value::Object(_) => true,
    }
}

// =============================================================================
// String Functions
// =============================================================================

/// Return the first `count` characters.
#[allow(non_snake_case)]
pub fn LEFT(text: &Value, count: &Value) -> Value {
    let s = S(text);
    let n = N(count) as usize;
    Value::String(s.chars().take(n).collect())
}

/// Return the last `count` characters.
#[allow(non_snake_case)]
pub fn RIGHT(text: &Value, count: &Value) -> Value {
    let s = S(text);
    let n = N(count) as usize;
    let len = s.chars().count();
    let skip = len.saturating_sub(n);
    Value::String(s.chars().skip(skip).collect())
}

/// Return `count` characters starting at 1-indexed `start`.
#[allow(non_snake_case)]
pub fn MID(text: &Value, start: &Value, count: &Value) -> Value {
    let s = S(text);
    let start_idx = (N(start) as usize).saturating_sub(1);
    let len = N(count) as usize;
    Value::String(s.chars().skip(start_idx).take(len).collect())
}

/// Case-sensitive search. Returns 1-indexed position or 0 if not found.
#[allow(non_snake_case)]
pub fn FIND(needle: &Value, haystack: &Value, start: Option<&Value>) -> Value {
    let n = S(needle);
    let h = S(haystack);
    let char_offset = start
        .map(|s| (N(s) as usize).saturating_sub(1))
        .unwrap_or(0);
    // Convert char offset to byte offset for safe slicing
    let byte_offset = h
        .char_indices()
        .nth(char_offset)
        .map(|(i, _)| i)
        .unwrap_or(h.len());
    match h[byte_offset..].find(&*n) {
        Some(byte_pos) => {
            // Convert byte position back to char position
            let char_pos = h[..byte_offset + byte_pos].chars().count();
            to_value((char_pos + 1) as f64)
        }
        None => to_value(0.0),
    }
}

/// Case-insensitive search. Returns 1-indexed position or 0 if not found.
#[allow(non_snake_case)]
pub fn SEARCH(needle: &Value, haystack: &Value, start: Option<&Value>) -> Value {
    let n = S(needle).to_lowercase();
    let h = S(haystack).to_lowercase();
    let char_offset = start
        .map(|s| (N(s) as usize).saturating_sub(1))
        .unwrap_or(0);
    let byte_offset = h
        .char_indices()
        .nth(char_offset)
        .map(|(i, _)| i)
        .unwrap_or(h.len());
    match h[byte_offset..].find(&*n) {
        Some(byte_pos) => {
            let char_pos = h[..byte_offset + byte_pos].chars().count();
            to_value((char_pos + 1) as f64)
        }
        None => to_value(0.0),
    }
}

/// Replace occurrences of `old` with `new_str`. If `index` is provided, only replace the Nth (1-based).
#[allow(non_snake_case)]
pub fn SUBSTITUTE(text: &Value, old: &Value, new_str: &Value, index: Option<&Value>) -> Value {
    let s = S(text);
    let old_s = S(old);
    let new_s = S(new_str);

    if old_s.is_empty() {
        return Value::String(s);
    }

    match index {
        None => Value::String(s.replace(&old_s, &new_s)),
        Some(idx) => {
            let target = N(idx) as usize;
            let mut count = 0usize;
            let mut result = String::new();
            let mut remaining = s.as_str();
            while let Some(pos) = remaining.find(&*old_s) {
                count += 1;
                if count == target {
                    result.push_str(&remaining[..pos]);
                    result.push_str(&new_s);
                    result.push_str(&remaining[pos + old_s.len()..]);
                    return Value::String(result);
                }
                result.push_str(&remaining[..pos + old_s.len()]);
                remaining = &remaining[pos + old_s.len()..];
            }
            result.push_str(remaining);
            Value::String(result)
        }
    }
}

/// Replace `count` characters at 1-indexed `start` with `replacement`.
#[allow(non_snake_case)]
pub fn REPLACE(text: &Value, start: &Value, count: &Value, replacement: &Value) -> Value {
    let s = S(text);
    let start_idx = (N(start) as usize).saturating_sub(1);
    let len = N(count) as usize;
    let repl = S(replacement);

    let before: String = s.chars().take(start_idx).collect();
    let after: String = s.chars().skip(start_idx + len).collect();
    Value::String(format!("{}{}{}", before, repl, after))
}

/// Return value only if it's a string, otherwise empty string.
#[allow(non_snake_case)]
pub fn T(v: &Value) -> Value {
    match v {
        Value::String(s) => Value::String(s.clone()),
        _ => Value::String(String::new()),
    }
}

/// Lowercase.
#[allow(non_snake_case)]
pub fn LOWER(text: &Value) -> Value {
    Value::String(S(text).to_lowercase())
}

/// Uppercase.
#[allow(non_snake_case)]
pub fn UPPER(text: &Value) -> Value {
    Value::String(S(text).to_uppercase())
}

/// Strip leading and trailing whitespace.
#[allow(non_snake_case)]
pub fn TRIM(text: &Value) -> Value {
    Value::String(S(text).trim().to_string())
}

/// String length (character count).
#[allow(non_snake_case)]
pub fn LEN(text: &Value) -> Value {
    to_value(S(text).chars().count() as f64)
}

/// Repeat string `count` times.
#[allow(non_snake_case)]
pub fn REPT(text: &Value, count: &Value) -> Value {
    let s = S(text);
    let n = N(count) as usize;
    Value::String(s.repeat(n))
}

/// Concatenate all values as strings.
#[allow(non_snake_case)]
pub fn CONCATENATE(args: &[Value]) -> Value {
    let result: String = args.iter().map(|v| S(v)).collect();
    Value::String(result)
}

/// URL-encode a string.
#[allow(non_snake_case)]
pub fn ENCODE_URL_COMPONENT(text: &Value) -> Value {
    let s = S(text);
    let mut encoded = String::new();
    for byte in s.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(byte as char);
            }
            _ => {
                encoded.push_str(&format!("%{:02X}", byte));
            }
        }
    }
    Value::String(encoded)
}

// =============================================================================
// Date/Time Functions
// =============================================================================

/// Coerce a value to DateTime<Utc>. null→None, number→Unix timestamp, string→ISO parse.
#[allow(non_snake_case)]
pub fn D(v: &Value) -> Option<DateTime<Utc>> {
    match v {
        Value::Null => None,
        Value::Number(n) => {
            let ts = n.as_f64()?;
            DateTime::from_timestamp(ts as i64, 0)
        }
        Value::String(s) => {
            let s = s.trim();
            if s.is_empty() {
                return None;
            }
            // Try full ISO 8601 with timezone
            if let Ok(dt) = DateTime::parse_from_rfc3339(s) {
                return Some(dt.with_timezone(&Utc));
            }
            // Try "YYYY-MM-DDTHH:MM:SS" without timezone (assume UTC)
            if let Ok(ndt) = NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S") {
                return Some(ndt.and_utc());
            }
            // Try date-only "YYYY-MM-DD"
            if let Ok(nd) = NaiveDate::parse_from_str(s, "%Y-%m-%d") {
                return nd.and_hms_opt(0, 0, 0).map(|ndt| ndt.and_utc());
            }
            None
        }
        Value::Array(arr) => arr.first().and_then(D),
        _ => None,
    }
}

fn date_to_iso(dt: &DateTime<Utc>) -> Value {
    Value::String(dt.format("%Y-%m-%dT%H:%M:%S%.3fZ").to_string())
}

fn parse_unit(v: Option<&Value>) -> String {
    v.map(|u| S(u).to_lowercase())
        .unwrap_or_else(|| "days".to_string())
}

/// Clamp day to valid range for given year/month.
fn clamp_day(year: i32, month: u32, day: u32) -> u32 {
    let max_day = NaiveDate::from_ymd_opt(year, month + 1, 1)
        .unwrap_or_else(|| NaiveDate::from_ymd_opt(year + 1, 1, 1).unwrap())
        .pred_opt()
        .unwrap()
        .day();
    day.min(max_day)
}

/// Today's date as "YYYY-MM-DD".
#[allow(non_snake_case)]
pub fn TODAY() -> Value {
    Value::String(Utc::now().format("%Y-%m-%d").to_string())
}

/// Current datetime as ISO string.
#[allow(non_snake_case)]
pub fn NOW() -> Value {
    date_to_iso(&Utc::now())
}

/// Add count units to a date.
#[allow(non_snake_case)]
pub fn DATEADD(date: &Value, count: &Value, unit: &Value) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return Value::Null,
    };
    let c = N(count) as i64;
    let u = S(unit).to_lowercase();

    let result = match u.as_str() {
        "years" => {
            let new_year = dt.year() + c as i32;
            let day = clamp_day(new_year, dt.month(), dt.day());
            dt.with_year(new_year)
                .and_then(|d| d.with_day(day))
                .unwrap_or(dt)
        }
        "months" => {
            let total_months = (dt.year() as i64) * 12 + (dt.month() as i64 - 1) + c;
            let new_year = (total_months.div_euclid(12)) as i32;
            let new_month = (total_months.rem_euclid(12) + 1) as u32;
            let day = clamp_day(new_year, new_month, dt.day());
            NaiveDate::from_ymd_opt(new_year, new_month, day)
                .and_then(|nd| nd.and_hms_opt(dt.hour(), dt.minute(), dt.second()))
                .map(|ndt| ndt.and_utc())
                .unwrap_or(dt)
        }
        "weeks" => dt + Duration::weeks(c),
        "days" => dt + Duration::days(c),
        "hours" => dt + Duration::hours(c),
        "minutes" => dt + Duration::minutes(c),
        "seconds" => dt + Duration::seconds(c),
        "milliseconds" => dt + Duration::milliseconds(c),
        _ => dt,
    };
    date_to_iso(&result)
}

/// Difference between two dates in the given unit.
#[allow(non_snake_case)]
pub fn DATETIME_DIFF(date1: &Value, date2: &Value, unit: Option<&Value>) -> Value {
    let d1 = match D(date1) {
        Some(d) => d,
        None => return to_value(0.0),
    };
    let d2 = match D(date2) {
        Some(d) => d,
        None => return to_value(0.0),
    };
    let u = parse_unit(unit);
    let diff = d1 - d2;

    let result = match u.as_str() {
        "milliseconds" => diff.num_milliseconds() as f64,
        "seconds" => diff.num_seconds() as f64,
        "minutes" => (diff.num_seconds() / 60) as f64,
        "hours" => (diff.num_seconds() / 3600) as f64,
        "days" => diff.num_days() as f64,
        "weeks" => (diff.num_days() / 7) as f64,
        "months" => ((d1.year() - d2.year()) * 12 + (d1.month() as i32 - d2.month() as i32)) as f64,
        "years" => (d1.year() - d2.year()) as f64,
        _ => diff.num_days() as f64,
    };
    to_value(result)
}

/// Format a date using Moment.js-style tokens.
#[allow(non_snake_case)]
pub fn DATETIME_FORMAT(date: &Value, fmt: Option<&Value>) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return Value::String(String::new()),
    };
    match fmt {
        None => date_to_iso(&dt),
        Some(f) => {
            let fmt_str = S(f);
            let mut result = String::new();
            let chars: Vec<char> = fmt_str.chars().collect();
            let mut i = 0;
            while i < chars.len() {
                if i + 4 <= chars.len() && &fmt_str[i..i + 4] == "YYYY" {
                    result.push_str(&format!("{:04}", dt.year()));
                    i += 4;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "YY" {
                    result.push_str(&format!("{:02}", dt.year() % 100));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "MM" {
                    result.push_str(&format!("{:02}", dt.month()));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "DD" {
                    result.push_str(&format!("{:02}", dt.day()));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "HH" {
                    result.push_str(&format!("{:02}", dt.hour()));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "hh" {
                    let h = dt.hour() % 12;
                    result.push_str(&format!("{:02}", if h == 0 { 12 } else { h }));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "mm" {
                    result.push_str(&format!("{:02}", dt.minute()));
                    i += 2;
                } else if i + 2 <= chars.len() && &fmt_str[i..i + 2] == "ss" {
                    result.push_str(&format!("{:02}", dt.second()));
                    i += 2;
                } else if chars[i] == 'A' {
                    result.push_str(if dt.hour() < 12 { "AM" } else { "PM" });
                    i += 1;
                } else if chars[i] == 'a' {
                    result.push_str(if dt.hour() < 12 { "am" } else { "pm" });
                    i += 1;
                } else {
                    result.push(chars[i]);
                    i += 1;
                }
            }
            Value::String(result)
        }
    }
}

/// Date portion "YYYY-MM-DD".
#[allow(non_snake_case)]
pub fn DATESTR(date: &Value) -> Value {
    match D(date) {
        Some(dt) => Value::String(dt.format("%Y-%m-%d").to_string()),
        None => Value::String(String::new()),
    }
}

/// Time portion "HH:MM:SS".
#[allow(non_snake_case)]
pub fn TIMESTR(date: &Value) -> Value {
    match D(date) {
        Some(dt) => Value::String(dt.format("%H:%M:%S").to_string()),
        None => Value::String(String::new()),
    }
}

/// Parse a date string and return as ISO string.
#[allow(non_snake_case)]
pub fn DATETIME_PARSE(date: &Value) -> Value {
    match D(date) {
        Some(dt) => date_to_iso(&dt),
        None => Value::Null,
    }
}

/// Regex extract first match. Returns null if no match.
#[allow(non_snake_case)]
pub fn REGEX_EXTRACT(text: &Value, pattern: &Value) -> Value {
    let t = S(text);
    let p = S(pattern);
    match Regex::new(&p) {
        Ok(re) => match re.find(&t) {
            Some(m) => Value::String(m.as_str().to_string()),
            None => Value::Null,
        },
        Err(_) => Value::Null,
    }
}

/// Regex match test. Returns true if pattern matches.
#[allow(non_snake_case)]
pub fn REGEX_MATCH(text: &Value, pattern: &Value) -> Value {
    let t = S(text);
    let p = S(pattern);
    match Regex::new(&p) {
        Ok(re) => Value::Bool(re.is_match(&t)),
        Err(_) => Value::Bool(false),
    }
}

/// Regex replace all matches.
#[allow(non_snake_case)]
pub fn REGEX_REPLACE(text: &Value, pattern: &Value, replacement: &Value) -> Value {
    let t = S(text);
    let p = S(pattern);
    let r = S(replacement);
    match Regex::new(&p) {
        Ok(re) => Value::String(re.replace_all(&t, r.as_str()).to_string()),
        Err(_) => Value::String(t),
    }
}

/// Convert a date to a different timezone.
#[allow(non_snake_case)]
pub fn SET_TIMEZONE(date: &Value, tz: &Value) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return Value::Null,
    };
    let tz_str = S(tz);
    let timezone: Tz = match tz_str.parse() {
        Ok(t) => t,
        Err(_) => return Value::Null,
    };
    let local = dt.with_timezone(&timezone);
    // Reconstruct as UTC with the local time values (matching Python/TS behavior)
    let ndt = NaiveDate::from_ymd_opt(local.year(), local.month(), local.day())
        .and_then(|nd| nd.and_hms_opt(local.hour(), local.minute(), local.second()))
        .map(|ndt| ndt.and_utc());
    match ndt {
        Some(dt) => date_to_iso(&dt),
        None => Value::Null,
    }
}

/// Extract year.
#[allow(non_snake_case)]
pub fn YEAR(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.year() as f64),
        None => to_value(0.0),
    }
}

/// Extract month (1-12).
#[allow(non_snake_case)]
pub fn MONTH(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.month() as f64),
        None => to_value(0.0),
    }
}

/// Extract day of month.
#[allow(non_snake_case)]
pub fn DAY(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.day() as f64),
        None => to_value(0.0),
    }
}

/// Extract hour (0-23).
#[allow(non_snake_case)]
pub fn HOUR(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.hour() as f64),
        None => to_value(0.0),
    }
}

/// Extract minute (0-59).
#[allow(non_snake_case)]
pub fn MINUTE(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.minute() as f64),
        None => to_value(0.0),
    }
}

/// Extract second (0-59).
#[allow(non_snake_case)]
pub fn SECOND(date: &Value) -> Value {
    match D(date) {
        Some(dt) => to_value(dt.second() as f64),
        None => to_value(0.0),
    }
}

/// Day of week: 0=Sunday, 1=Monday, ..., 6=Saturday.
#[allow(non_snake_case)]
pub fn WEEKDAY(date: &Value) -> Value {
    match D(date) {
        Some(dt) => {
            let dow = dt.weekday().num_days_from_sunday();
            to_value(dow as f64)
        }
        None => to_value(0.0),
    }
}

/// Week number of the year.
#[allow(non_snake_case)]
pub fn WEEKNUM(date: &Value, start_day: Option<&Value>) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return to_value(0.0),
    };

    let start_dow = match start_day {
        Some(v) => match S(v).to_lowercase().as_str() {
            "monday" => Weekday::Mon,
            "tuesday" => Weekday::Tue,
            "wednesday" => Weekday::Wed,
            "thursday" => Weekday::Thu,
            "friday" => Weekday::Fri,
            "saturday" => Weekday::Sat,
            _ => Weekday::Sun,
        },
        None => Weekday::Sun,
    };

    let jan1 = NaiveDate::from_ymd_opt(dt.year(), 1, 1).unwrap();
    let day_of_year = dt.ordinal0() as i32;
    let jan1_dow = jan1.weekday().num_days_from_sunday() as i32;
    let start_offset = start_dow.num_days_from_sunday() as i32;
    let adjusted = day_of_year + ((jan1_dow - start_offset + 7) % 7);
    to_value((adjusted / 7 + 1) as f64)
}

fn human_duration(d1: DateTime<Utc>, d2: DateTime<Utc>) -> String {
    let diff = if d1 > d2 { d1 - d2 } else { d2 - d1 };
    let total_secs = diff.num_seconds().unsigned_abs();
    let total_mins = total_secs / 60;
    let total_hours = total_mins / 60;
    let total_days = total_hours / 24;

    let years = total_days / 365;
    if years > 0 {
        return if years == 1 {
            "1 year".to_string()
        } else {
            format!("{} years", years)
        };
    }
    let months = total_days / 30;
    if months > 0 {
        return if months == 1 {
            "1 month".to_string()
        } else {
            format!("{} months", months)
        };
    }
    if total_days > 0 {
        return if total_days == 1 {
            "1 day".to_string()
        } else {
            format!("{} days", total_days)
        };
    }
    if total_hours > 0 {
        return if total_hours == 1 {
            "1 hour".to_string()
        } else {
            format!("{} hours", total_hours)
        };
    }
    if total_mins > 0 {
        return if total_mins == 1 {
            "1 minute".to_string()
        } else {
            format!("{} minutes", total_mins)
        };
    }
    if total_secs == 1 {
        "1 second".to_string()
    } else {
        format!("{} seconds", total_secs)
    }
}

/// Time elapsed from date until now. With unit returns number, without returns human-readable string.
#[allow(non_snake_case)]
pub fn TONOW(date: &Value, unit: Option<&Value>) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return Value::Null,
    };
    let now = Utc::now();
    match unit {
        Some(_) => DATETIME_DIFF(&date_to_iso(&now), &date_to_iso(&dt), unit),
        None => Value::String(human_duration(now, dt)),
    }
}

/// Time from now until date. With unit returns number, without returns human-readable string.
#[allow(non_snake_case)]
pub fn FROMNOW(date: &Value, unit: Option<&Value>) -> Value {
    let dt = match D(date) {
        Some(d) => d,
        None => return Value::Null,
    };
    let now = Utc::now();
    match unit {
        Some(_) => DATETIME_DIFF(&date_to_iso(&dt), &date_to_iso(&now), unit),
        None => Value::String(human_duration(dt, now)),
    }
}

/// Check if two dates are the same at the given unit granularity.
#[allow(non_snake_case)]
pub fn IS_SAME(date1: &Value, date2: &Value, unit: Option<&Value>) -> Value {
    let default = Value::String("days".to_string());
    let u = unit.unwrap_or(&default);
    let diff = DATETIME_DIFF(date1, date2, Some(u));
    Value::Bool(diff == serde_json::json!(0))
}

/// Check if date1 is before date2.
#[allow(non_snake_case)]
pub fn IS_BEFORE(date1: &Value, date2: &Value, unit: Option<&Value>) -> Value {
    let default = Value::String("days".to_string());
    let u = unit.unwrap_or(&default);
    let diff = DATETIME_DIFF(date1, date2, Some(u));
    Value::Bool(N(&diff) < 0.0)
}

/// Check if date1 is after date2.
#[allow(non_snake_case)]
pub fn IS_AFTER(date1: &Value, date2: &Value, unit: Option<&Value>) -> Value {
    let default = Value::String("days".to_string());
    let u = unit.unwrap_or(&default);
    let diff = DATETIME_DIFF(date1, date2, Some(u));
    Value::Bool(N(&diff) > 0.0)
}

/// Add workdays (skip Saturday and Sunday).
#[allow(non_snake_case)]
pub fn WORKDAY(start: &Value, num_days: &Value) -> Value {
    let mut dt = match D(start) {
        Some(d) => d,
        None => return Value::Null,
    };
    let mut remaining = N(num_days) as i64;
    let direction = if remaining >= 0 { 1 } else { -1 };
    remaining = remaining.abs();

    while remaining > 0 {
        dt = dt + Duration::days(direction);
        let wd = dt.weekday();
        if wd != Weekday::Sat && wd != Weekday::Sun {
            remaining -= 1;
        }
    }
    date_to_iso(&dt)
}

/// Count workdays between two dates (includes start day if it's a workday).
#[allow(non_snake_case)]
pub fn WORKDAY_DIFF(start: &Value, end: &Value) -> Value {
    let d1 = match D(start) {
        Some(d) => d,
        None => return to_value(0.0),
    };
    let d2 = match D(end) {
        Some(d) => d,
        None => return to_value(0.0),
    };

    let mut count = 0i64;
    let mut current = d1;
    let direction = if d2 >= d1 { 1 } else { -1 };

    // Include start day if it's a workday
    if current.weekday() != Weekday::Sat && current.weekday() != Weekday::Sun {
        count += direction;
    }

    while (direction == 1 && current < d2) || (direction == -1 && current > d2) {
        current = current + Duration::days(direction);
        let wd = current.weekday();
        if wd != Weekday::Sat && wd != Weekday::Sun {
            count += direction;
        }
    }
    to_value(count as f64)
}

// =============================================================================
// Array Functions
// =============================================================================

/// Join array elements into a string with separator (default ", ").
#[allow(non_snake_case)]
pub fn ARRAYJOIN(arr: &Value, separator: Option<&Value>) -> Value {
    let sep = separator.map(|v| S(v)).unwrap_or_else(|| ", ".to_string());
    match arr {
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(|v| S(v)).collect();
            Value::String(parts.join(&sep))
        }
        _ => Value::String(S(arr)),
    }
}

/// Remove duplicate values, preserving order.
#[allow(non_snake_case)]
pub fn ARRAYUNIQUE(arr: &Value) -> Value {
    match arr {
        Value::Array(items) => {
            let mut seen = Vec::new();
            for v in items {
                if !seen.contains(v) {
                    seen.push(v.clone());
                }
            }
            Value::Array(seen)
        }
        _ => Value::Array(vec![arr.clone()]),
    }
}

/// Remove null and empty string values.
#[allow(non_snake_case)]
pub fn ARRAYCOMPACT(arr: &Value) -> Value {
    match arr {
        Value::Array(items) => {
            let filtered: Vec<Value> = items
                .iter()
                .filter(|v| !v.is_null() && *v != &Value::String(String::new()))
                .cloned()
                .collect();
            Value::Array(filtered)
        }
        Value::Null => Value::Array(vec![]),
        _ => Value::Array(vec![arr.clone()]),
    }
}

/// Recursively flatten nested arrays.
#[allow(non_snake_case)]
pub fn ARRAYFLATTEN(arr: &Value) -> Value {
    fn flatten_recursive(v: &Value, out: &mut Vec<Value>) {
        match v {
            Value::Array(items) => {
                for item in items {
                    flatten_recursive(item, out);
                }
            }
            _ => out.push(v.clone()),
        }
    }

    match arr {
        Value::Array(_) => {
            let mut result = Vec::new();
            flatten_recursive(arr, &mut result);
            Value::Array(result)
        }
        _ => Value::Array(vec![arr.clone()]),
    }
}
