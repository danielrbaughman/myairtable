package airtable

// MaybeSpecialOrError[T] models a computed field value that is normally a T but
// can instead be an Airtable "special number" ({"specialValue": "NaN"|...}) or
// an error ({"error": "#ERROR!"}). Decoding dispatches on the object shape.

import "encoding/json"

// SpecialNumber is Airtable's non-finite-number sentinel, e.g. {"specialValue":"NaN"}.
type SpecialNumber struct {
	SpecialValue string `json:"specialValue"`
}

// ErrorValue is Airtable's computed-field error sentinel, e.g. {"error":"#ERROR!"}.
type ErrorValue struct {
	Error string `json:"error"`
}

type MaybeSpecialOrError[T any] struct {
	value    T
	hasValue bool
	special  *SpecialNumber
	errValue *ErrorValue
}

// Value returns the contained value and whether it is present (false when the
// field decoded to a special number or an error instead).
func (m MaybeSpecialOrError[T]) Value() (T, bool) { return m.value, m.hasValue }

// IsSpecial reports whether the value is a special number; Special returns it.
func (m MaybeSpecialOrError[T]) IsSpecial() bool         { return m.special != nil }
func (m MaybeSpecialOrError[T]) Special() *SpecialNumber { return m.special }

// IsError reports whether the value is an error; ErrorVal returns it.
func (m MaybeSpecialOrError[T]) IsError() bool         { return m.errValue != nil }
func (m MaybeSpecialOrError[T]) ErrorVal() *ErrorValue { return m.errValue }

func (m *MaybeSpecialOrError[T]) UnmarshalJSON(b []byte) error {
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(b, &probe); err == nil {
		if _, ok := probe["specialValue"]; ok {
			var sn SpecialNumber
			if err := json.Unmarshal(b, &sn); err != nil {
				return err
			}
			m.special = &sn
			return nil
		}
		if _, ok := probe["error"]; ok {
			var ev ErrorValue
			if err := json.Unmarshal(b, &ev); err != nil {
				return err
			}
			m.errValue = &ev
			return nil
		}
	}
	if err := json.Unmarshal(b, &m.value); err != nil {
		return err
	}
	m.hasValue = true
	return nil
}

func (m MaybeSpecialOrError[T]) MarshalJSON() ([]byte, error) {
	switch {
	case m.special != nil:
		return json.Marshal(m.special)
	case m.errValue != nil:
		return json.Marshal(m.errValue)
	case m.hasValue:
		return json.Marshal(m.value)
	default:
		return []byte("null"), nil
	}
}
