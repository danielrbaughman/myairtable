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
