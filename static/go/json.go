package airtable

// Date and Duration wire types + the shared value-boxing helper used by payload
// builders and the formula runtime. Airtable JSON has no library equivalents:
// dates arrive in three formats, durations as numeric seconds.

import (
	"bytes"
	"encoding/json"
	"strconv"
	"time"
)

// dateLayouts are tried in order when decoding an Airtable date/time string:
// fractional RFC3339, plain RFC3339, then date-only (interpreted as midnight UTC).
var dateLayouts = []string{time.RFC3339Nano, time.RFC3339, "2006-01-02"}

// AirtableTime wraps time.Time with Airtable's multi-format decoding. Plain
// time.Time cannot parse date-only values, so date/datetime fields use this.
type AirtableTime struct {
	time.Time
}

func (t *AirtableTime) UnmarshalJSON(b []byte) error {
	trimmed := bytes.TrimSpace(b)
	if string(trimmed) == "null" {
		return nil
	}
	var s string
	if err := json.Unmarshal(trimmed, &s); err != nil {
		return &DecodingError{Err: err}
	}
	for _, layout := range dateLayouts {
		if parsed, err := time.Parse(layout, s); err == nil {
			t.Time = parsed.UTC()
			return nil
		}
	}
	return &DecodingError{Err: &time.ParseError{Value: s, Message: " is not a recognized Airtable date format"}}
}

func (t AirtableTime) MarshalJSON() ([]byte, error) {
	return json.Marshal(t.Time.UTC().Format(time.RFC3339))
}

// AirtableDuration is a time.Duration whose wire format is numeric seconds
// (Airtable encodes durations as a number of seconds, not nanoseconds or ISO).
type AirtableDuration time.Duration

func (d AirtableDuration) MarshalJSON() ([]byte, error) {
	secs := time.Duration(d).Seconds()
	return []byte(strconv.FormatFloat(secs, 'f', -1, 64)), nil
}

func (d *AirtableDuration) UnmarshalJSON(b []byte) error {
	trimmed := bytes.TrimSpace(b)
	if string(trimmed) == "null" {
		return nil
	}
	secs, err := strconv.ParseFloat(string(trimmed), 64)
	if err != nil {
		return &DecodingError{Err: err}
	}
	*d = AirtableDuration(time.Duration(secs * float64(time.Second)))
	return nil
}

// Duration returns the value as a standard time.Duration.
func (d AirtableDuration) Duration() time.Duration { return time.Duration(d) }

// V boxes an arbitrary Go value into the native `any` representation the formula
// runtime operates on (the values it sees after JSON decode: nil/bool/float64/
// string/[]any/map). Scalar pointers are dereferenced (a nil pointer becomes
// nil), and the Airtable wrapper types are unwrapped to a runtime-coercible
// form — AirtableTime -> time.Time (so D() handles it), AirtableDuration ->
// seconds as float64 (so N() can do arithmetic on durations). Anything else
// (slices, maps, plain scalars) is returned unchanged.
func V(value any) any {
	switch v := value.(type) {
	case nil:
		return nil
	case *string:
		if v == nil {
			return nil
		}
		return *v
	case *float64:
		if v == nil {
			return nil
		}
		return *v
	case *int64:
		if v == nil {
			return nil
		}
		return *v
	case *bool:
		if v == nil {
			return nil
		}
		return *v
	case AirtableTime:
		return v.Time
	case *AirtableTime:
		if v == nil {
			return nil
		}
		return v.Time
	case AirtableDuration:
		return time.Duration(v).Seconds()
	case *AirtableDuration:
		if v == nil {
			return nil
		}
		return time.Duration(*v).Seconds()
	default:
		return value
	}
}

// marshalField encodes a single writable field value for a create/update
// payload, returning the raw JSON bytes.
func marshalField(value any) (json.RawMessage, error) {
	b, err := json.Marshal(value)
	if err != nil {
		return nil, &DecodingError{Err: err}
	}
	return b, nil
}
