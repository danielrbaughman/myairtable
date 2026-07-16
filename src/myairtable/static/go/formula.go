// ==========================================
// MyAirtable static runtime.
// ==========================================

package airtable

import "strings"

// Formula wraps an Airtable filterByFormula expression string. It is the value
// every field-builder method returns; combine instances with And/Or/Not/Xor and
// render the final string with String() (or pass it to Query.WithFilterFormula).
//
// Filter strings reference Airtable FIELD NAMES — {Field Name} — not field IDs.
type Formula struct {
	expr string
}

// NewFormula wraps a raw expression string in a Formula. Rarely needed directly;
// the field builders and combinators produce Formula values for you.
func NewFormula(expr string) Formula { return Formula{expr: expr} }

// String renders the filterByFormula expression. Implements fmt.Stringer so a
// Formula can be passed straight to Query.WithFilter via f.String().
func (f Formula) String() string { return f.expr }

// IsEmpty reports whether this Formula carries no expression (the zero value,
// produced e.g. by And() over an empty/all-empty argument list).
func (f Formula) IsEmpty() bool { return f.expr == "" }

// WithFilterFormula sets filterByFormula from a Formula. Convenience over
// WithFilter(f.String()).
func (q *Query) WithFilterFormula(f Formula) *Query { q.Filter = f.String(); return q }

// =============================================================================
// Combinators — Airtable's logical functions.
// =============================================================================

// And combines formulas with AND logic. Empty formulas are filtered out; zero
// surviving args yields the empty Formula, one yields it bare, more wrap in AND().
func And(args ...Formula) Formula { return combine("AND", args) }

// Or combines formulas with OR logic. Empty formulas are filtered out.
func Or(args ...Formula) Formula { return combine("OR", args) }

// Xor combines formulas with exclusive-OR logic. Empty formulas are filtered out.
func Xor(args ...Formula) Formula { return combine("XOR", args) }

// Not negates a formula.
func Not(f Formula) Formula { return Formula{expr: "NOT(" + f.expr + ")"} }

func combine(fn string, args []Formula) Formula {
	filtered := make([]string, 0, len(args))
	for _, a := range args {
		if a.expr != "" {
			filtered = append(filtered, a.expr)
		}
	}
	switch len(filtered) {
	case 0:
		return Formula{}
	case 1:
		return Formula{expr: filtered[0]}
	default:
		return Formula{expr: fn + "(" + strings.Join(filtered, ",") + ")"}
	}
}

// =============================================================================
// Shared escaping / wrapping helpers (package-private).
// =============================================================================

// escapeFormulaString escapes a value for an Airtable double-quoted formula
// string. Backslashes are escaped FIRST, then quotes — otherwise a trailing `\`
// leaves the closing quote live and the remainder executes as formula code.
func escapeFormulaString(value string) string {
	value = strings.ReplaceAll(value, "\\", "\\\\")
	return strings.ReplaceAll(value, "\"", "\\\"")
}

// escapeFormulaStringSingle escapes a value for an Airtable single-quoted string.
func escapeFormulaStringSingle(value string) string {
	value = strings.ReplaceAll(value, "\\", "\\\\")
	return strings.ReplaceAll(value, "'", "\\'")
}

func wrapField(field string, caseSensitive, trim bool) string {
	v := field
	if trim {
		v = "TRIM(" + v + ")"
	}
	if !caseSensitive {
		v = "LOWER(" + v + ")"
	}
	return v
}

func wrapValueStr(value string, caseSensitive, trim bool) string {
	v := "\"" + escapeFormulaString(value) + "\""
	if trim {
		v = "TRIM(" + v + ")"
	}
	if !caseSensitive {
		v = "LOWER(" + v + ")"
	}
	return v
}
