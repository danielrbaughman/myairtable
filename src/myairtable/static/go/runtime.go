package airtable

// Formula runtime: value coercions operating on the native `any` representation
// of decoded JSON (nil, bool, float64, string, []any, map[string]any). These
// match the Java/Kotlin/Rust AirtableRuntime semantics exactly so transpiled
// formula evaluation agrees with the Airtable API. The ~80 formula functions
// (math/logic/string/date/array/regex) are added in F8; coercions live here.

import (
	"math"
	"strconv"
	"strings"
	"time"
)

// N coerces a value to a number, mirroring Airtable's numeric coercion.
func N(value any) float64 {
	switch v := value.(type) {
	case nil:
		return 0
	case float64:
		return v
	case int64:
		return float64(v)
	case int:
		return float64(v)
	case bool:
		if v {
			return 1
		}
		return 0
	case string:
		if f, err := strconv.ParseFloat(trimSpace(v), 64); err == nil {
			return f
		}
		return 0
	case []any:
		if len(v) == 0 {
			return 0
		}
		return N(v[0])
	default:
		return 0
	}
}

// S coerces a value to a string, mirroring Airtable's string coercion (note:
// false -> "0", and arrays coerce to their first element, not a join).
func S(value any) string {
	switch v := value.(type) {
	case nil:
		return ""
	case string:
		return v
	case bool:
		if v {
			return "1"
		}
		return "0"
	case float64:
		if isIntegral(v) {
			return strconv.FormatInt(int64(v), 10)
		}
		return strconv.FormatFloat(v, 'g', -1, 64)
	case int64:
		return strconv.FormatInt(v, 10)
	case int:
		return strconv.Itoa(v)
	case []any:
		// Airtable coerces a multi-value field to a string by joining with ", ", not first element.
		parts := make([]string, len(v))
		for i, e := range v {
			parts[i] = S(e)
		}
		return strings.Join(parts, ", ")
	default:
		return ""
	}
}

// IsTruthy reports the Airtable truthiness of a value.
func IsTruthy(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case string:
		return v != ""
	case bool:
		return v
	case float64:
		return v != 0 && !math.IsNaN(v)
	case int64:
		return v != 0
	case int:
		return v != 0
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	default:
		return false
	}
}

// A flattens its arguments into a single slice: array args are spread, nil args
// are dropped, scalar args are appended.
func A(args ...any) []any {
	result := make([]any, 0, len(args))
	for _, arg := range args {
		switch v := arg.(type) {
		case nil:
			continue
		case []any:
			result = append(result, v...)
		default:
			result = append(result, v)
		}
	}
	return result
}

// AN flattens its arguments and coerces each to a number.
func AN(args ...any) []float64 {
	flat := A(args...)
	result := make([]float64, len(flat))
	for i, v := range flat {
		result[i] = N(v)
	}
	return result
}

// AS flattens its arguments and coerces each to a string.
func AS(args ...any) []string {
	flat := A(args...)
	result := make([]string, len(flat))
	for i, v := range flat {
		result[i] = S(v)
	}
	return result
}

// D coerces a value to a time.Time (zero time when not parseable).
func D(value any) time.Time {
	switch v := value.(type) {
	case time.Time:
		return v
	case AirtableTime:
		return v.Time
	case *AirtableTime:
		if v != nil {
			return v.Time
		}
	case string:
		for _, layout := range dateLayouts {
			if parsed, err := time.Parse(layout, v); err == nil {
				return parsed.UTC()
			}
		}
	case float64:
		return time.UnixMilli(int64(v * 1000)).UTC()
	case int64:
		return time.UnixMilli(v * 1000).UTC()
	case int:
		return time.UnixMilli(int64(v) * 1000).UTC()
	case []any:
		if len(v) > 0 {
			return D(v[0])
		}
	}
	return time.Time{}
}

// IsEqual reports Airtable equality between two native values when neither side's
// type is statically inferable (the transpiler routes numeric/string comparisons
// through N()/S() directly). Two numbers compare numerically; otherwise both are
// string-coerced — matching Airtable's `=` operator coercion.
func IsEqual(a, b any) bool {
	if isNumber(a) && isNumber(b) {
		return N(a) == N(b)
	}
	return S(a) == S(b)
}

func isIntegral(d float64) bool {
	return !math.IsInf(d, 0) && !math.IsNaN(d) && d == math.Floor(d) && math.Abs(d) < 1e15
}

func trimSpace(s string) string {
	start, end := 0, len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\n' || s[start] == '\r') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n' || s[end-1] == '\r') {
		end--
	}
	return s[start:end]
}
