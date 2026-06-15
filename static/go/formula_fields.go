// ==========================================
// MyAirtable static runtime.
// ==========================================

package airtable

import (
	"strconv"
	"strings"
)

// Filter strings reference Airtable FIELD NAMES — {Field Name}. Every builder is
// constructed with the field's display name (the generator passes the generated
// {Prefix}{Field}FieldName constant).

// fieldRef wraps a field name as an Airtable reference: {Field Name}.
func fieldRef(name string) string { return "{" + name + "}" }

// numberToString renders a numeric value the way Airtable formula source expects:
// integers without a trailing ".0", floats with their natural decimal form.
// Uses 'f' (never 'g'/'e') so values >= 1e6 are NOT emitted in scientific
// notation — Airtable's formula parser rejects "1e+06", which would silently
// break numeric filters on large values (e.g. currency).
func numberToString(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

// =============================================================================
// Shared text operations (text, select, lookup fields).
// =============================================================================

// textOps holds a field name plus the reference used for string operations
// (FIND/LEN with LOWER/TRIM). Lookup fields override stringField with an
// ARRAYJOIN wrapper so Airtable coerces the array to a string.
type textOps struct {
	name        string
	stringField string
}

func newTextOps(name string) textOps {
	ref := fieldRef(name)
	return textOps{name: ref, stringField: ref}
}

func (t textOps) field() string { return t.name }

// Empty: field is blank.
func (t textOps) IsEmpty() Formula { return Formula{expr: t.field() + "=BLANK()"} }

// NotEmpty: field is not blank.
func (t textOps) IsNotEmpty() Formula { return Formula{expr: t.field() + "!=BLANK()"} }

// Eq: exact equality. Named Eq (not Equals) for cross-language parity.
func (t textOps) Eq(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.field(), caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: f + "=" + v}
}

// EqualsAny: equals any of the given values.
func (t textOps) EqualsAny(values []string, caseSensitive, trim bool) Formula {
	parts := make([]Formula, 0, len(values))
	for _, v := range values {
		parts = append(parts, t.Eq(v, caseSensitive, trim))
	}
	return Or(parts...)
}

// Neq: not equal.
func (t textOps) Neq(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.field(), caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: f + "!=" + v}
}

// Contains: contains substring.
func (t textOps) Contains(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.stringField, caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: "FIND(" + v + "," + f + ")>0"}
}

// ContainsAny: contains any of the given values.
func (t textOps) ContainsAny(values []string, caseSensitive, trim bool) Formula {
	parts := make([]Formula, 0, len(values))
	for _, v := range values {
		parts = append(parts, t.Contains(v, caseSensitive, trim))
	}
	return Or(parts...)
}

// ContainsAll: contains all of the given values.
func (t textOps) ContainsAll(values []string, caseSensitive, trim bool) Formula {
	parts := make([]Formula, 0, len(values))
	for _, v := range values {
		parts = append(parts, t.Contains(v, caseSensitive, trim))
	}
	return And(parts...)
}

// NotContains: does not contain substring.
func (t textOps) NotContains(value string, caseSensitive, trim bool) Formula {
	return Not(t.Contains(value, caseSensitive, trim))
}

// StartsWith: starts with the given value.
func (t textOps) StartsWith(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.stringField, caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: "FIND(" + v + "," + f + ")=1"}
}

// NotStartsWith: does not start with the given value.
func (t textOps) NotStartsWith(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.stringField, caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: "FIND(" + v + "," + f + ")!=1"}
}

// EndsWith: ends with the given value.
func (t textOps) EndsWith(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.stringField, caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: "FIND(" + v + "," + f + ")=LEN(" + f + ")-LEN(" + v + ")+1"}
}

// NotEndsWith: does not end with the given value.
func (t textOps) NotEndsWith(value string, caseSensitive, trim bool) Formula {
	f := wrapField(t.stringField, caseSensitive, trim)
	v := wrapValueStr(value, caseSensitive, trim)
	return Formula{expr: "FIND(" + v + "," + f + ")!=LEN(" + f + ")-LEN(" + v + ")+1"}
}

// PhoneEquals: phone-number equality (strips spaces, dashes, parens, plus, dots).
func (t textOps) PhoneEquals(value string) Formula {
	var normalized strings.Builder
	for _, c := range value {
		if !strings.ContainsRune(" -().+", c) {
			normalized.WriteRune(c)
		}
	}
	stripped := "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(" +
		t.field() +
		",\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")"
	return Formula{expr: stripped + "=\"" + escapeFormulaString(normalized.String()) + "\""}
}

// RegexMatch: regex match.
func (t textOps) RegexMatch(pattern string) Formula {
	return Formula{expr: "REGEX_MATCH(" + t.field() + ",\"" + escapeFormulaString(pattern) + "\")"}
}

// =============================================================================
// TextField
// =============================================================================

// TextField is the formula builder for text fields (single/long text, url, email,
// phone, barcode, rich text).
type TextField struct{ textOps }

// NewTextField builds a TextField for the given Airtable field name.
func NewTextField(name string) TextField { return TextField{newTextOps(name)} }

// =============================================================================
// SingleSelectField / MultiSelectField
// =============================================================================

// SingleSelectField is the formula builder for single-select fields.
type SingleSelectField struct{ textOps }

// NewSingleSelectField builds a SingleSelectField for the given field name.
func NewSingleSelectField(name string) SingleSelectField {
	return SingleSelectField{newTextOps(name)}
}

// MultiSelectField is the formula builder for multi-select fields.
type MultiSelectField struct{ textOps }

// NewMultiSelectField builds a MultiSelectField for the given field name.
func NewMultiSelectField(name string) MultiSelectField {
	return MultiSelectField{newTextOps(name)}
}

// =============================================================================
// LookupField
// =============================================================================

// LookupField is the formula builder for lookup (multipleLookupValues) fields.
//
// Lookup values are arrays. Airtable does not auto-coerce arrays through
// LOWER/TRIM/FIND, so string ops would silently match nothing; the string
// reference is wrapped in ARRAYJOIN(field, ", ") so they see a string. Equality
// (=) is unaffected — Airtable coerces array fields to a comma-joined string.
type LookupField struct{ textOps }

// NewLookupField builds a LookupField for the given field name.
func NewLookupField(name string) LookupField {
	ops := newTextOps(name)
	ops.stringField = "ARRAYJOIN(" + fieldRef(name) + ", \", \")"
	return LookupField{ops}
}

// =============================================================================
// NumberField
// =============================================================================

// NumberField is the formula builder for numeric fields (number, currency,
// percent, count, duration, autoNumber).
type NumberField struct{ name string }

// NewNumberField builds a NumberField for the given field name.
func NewNumberField(name string) NumberField { return NumberField{name: fieldRef(name)} }

func (n NumberField) field() string { return n.name }

// IsEmpty: field is blank.
func (n NumberField) IsEmpty() Formula { return Formula{expr: n.field() + "=BLANK()"} }

// IsNotEmpty: field is not blank.
func (n NumberField) IsNotEmpty() Formula { return Formula{expr: n.field() + "!=BLANK()"} }

// Eq: equal to value.
func (n NumberField) Eq(value float64) Formula {
	return Formula{expr: n.field() + "=" + numberToString(value)}
}

// Neq: not equal to value.
func (n NumberField) Neq(value float64) Formula {
	return Formula{expr: n.field() + "!=" + numberToString(value)}
}

// GreaterThan: greater than value.
func (n NumberField) GreaterThan(value float64) Formula {
	return Formula{expr: n.field() + ">" + numberToString(value)}
}

// LessThan: less than value.
func (n NumberField) LessThan(value float64) Formula {
	return Formula{expr: n.field() + "<" + numberToString(value)}
}

// GreaterThanOrEqual: greater than or equal to value.
func (n NumberField) GreaterThanOrEqual(value float64) Formula {
	return Formula{expr: n.field() + ">=" + numberToString(value)}
}

// LessThanOrEqual: less than or equal to value.
func (n NumberField) LessThanOrEqual(value float64) Formula {
	return Formula{expr: n.field() + "<=" + numberToString(value)}
}

// Between: between min and max. inclusive selects >=/<= vs >/<.
func (n NumberField) Between(min, max float64, inclusive bool) Formula {
	if inclusive {
		return And(n.GreaterThanOrEqual(min), n.LessThanOrEqual(max))
	}
	return And(n.GreaterThan(min), n.LessThan(max))
}

// =============================================================================
// BooleanField
// =============================================================================

// BooleanField is the formula builder for checkbox/boolean fields.
type BooleanField struct{ name string }

// NewBooleanField builds a BooleanField for the given field name.
func NewBooleanField(name string) BooleanField { return BooleanField{name: fieldRef(name)} }

func (b BooleanField) field() string { return b.name }

// IsTrue: field is checked/true.
func (b BooleanField) IsTrue() Formula { return Formula{expr: b.field() + "=TRUE()"} }

// IsFalse: field is unchecked/false.
func (b BooleanField) IsFalse() Formula { return Formula{expr: b.field() + "=FALSE()"} }

// Eq: equal to boolean value.
func (b BooleanField) Eq(value bool) Formula {
	if value {
		return b.IsTrue()
	}
	return b.IsFalse()
}

// =============================================================================
// AttachmentsField
// =============================================================================

// AttachmentsField is the formula builder for attachment fields.
type AttachmentsField struct{ name string }

// NewAttachmentsField builds an AttachmentsField for the given field name.
func NewAttachmentsField(name string) AttachmentsField {
	return AttachmentsField{name: fieldRef(name)}
}

func (a AttachmentsField) field() string { return a.name }

// Count: has exactly n attachments.
func (a AttachmentsField) Count(n int) Formula {
	return Formula{expr: "LEN(" + a.field() + ")=" + strconv.Itoa(n)}
}

// IsEmpty: has no attachments.
func (a AttachmentsField) IsEmpty() Formula {
	return Formula{expr: "LEN(" + a.field() + ")=0"}
}

// IsNotEmpty: has attachments.
func (a AttachmentsField) IsNotEmpty() Formula {
	return Formula{expr: "LEN(" + a.field() + ")>0"}
}

// =============================================================================
// IDField — record IDs (RECORD_ID()).
// =============================================================================

// IDField is the formula builder for record-ID filters.
type IDField struct{}

// NewIDField builds an IDField. (Takes no field name; RECORD_ID() is implicit.)
func NewIDField() IDField { return IDField{} }

// Eq: match a specific record ID.
func (IDField) Eq(id string) Formula {
	return Formula{expr: "RECORD_ID()='" + escapeFormulaStringSingle(id) + "'"}
}

// InList: match any of the given record IDs.
func (i IDField) InList(ids []string) Formula {
	switch len(ids) {
	case 0:
		return Formula{expr: "FALSE()"}
	case 1:
		return i.Eq(ids[0])
	default:
		parts := make([]Formula, 0, len(ids))
		for _, id := range ids {
			parts = append(parts, i.Eq(id))
		}
		return Or(parts...)
	}
}
