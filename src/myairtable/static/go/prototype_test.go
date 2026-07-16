package airtable

// PHASE 0 GATE (G1.12 / go-plan-v2 §F1.12).
//
// Proves the four CRIT design risks of the Go target compile AND run correctly,
// BEFORE any generator templating is built on top of them. Uses throwaway,
// test-only (lowercase) types so it never collides with the real runtime types
// (VecOrValue, MaybeSpecialOrError, AirtableTime, ...) that F2 introduces — the
// mechanisms exercised here (encoding/json reflection dispatch, generic pointer
// constraints) are language-level and behave identically for the real types.
//
// If any of these fail, the plan's core assumptions are wrong and must be
// revised before proceeding.

import (
	"bytes"
	"context"
	"encoding/json"
	"strconv"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// CRIT-4: nested generic decode — does json.Unmarshal dispatch to a type
// parameter's pointer-receiver UnmarshalJSON for vov[msoe[T]]?
// ---------------------------------------------------------------------------

type protoMSOE[T any] struct {
	value     T
	special   string
	isSpecial bool
}

func (m *protoMSOE[T]) UnmarshalJSON(b []byte) error {
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(b, &probe); err == nil {
		if sv, ok := probe["specialValue"]; ok {
			m.isSpecial = true
			return json.Unmarshal(sv, &m.special)
		}
	}
	return json.Unmarshal(b, &m.value)
}

type protoVOV[T any] struct {
	single   T
	multiple []T
	isMulti  bool
}

func (v *protoVOV[T]) UnmarshalJSON(b []byte) error {
	trimmed := bytes.TrimSpace(b)
	if len(trimmed) > 0 && trimmed[0] == '[' {
		v.isMulti = true
		return json.Unmarshal(b, &v.multiple)
	}
	return json.Unmarshal(b, &v.single)
}

func TestProtoNestedGenericDecode(t *testing.T) {
	// Single MSOE[string], plain value.
	var single protoMSOE[string]
	if err := json.Unmarshal([]byte(`"hello"`), &single); err != nil {
		t.Fatalf("single decode: %v", err)
	}
	if single.isSpecial || single.value != "hello" {
		t.Fatalf("single: got %+v", single)
	}

	// Single MSOE[string], special-value shape.
	var special protoMSOE[string]
	if err := json.Unmarshal([]byte(`{"specialValue":"NaN"}`), &special); err != nil {
		t.Fatalf("special decode: %v", err)
	}
	if !special.isSpecial || special.special != "NaN" {
		t.Fatalf("special: got %+v", special)
	}

	// THE CRIT CASE: VOV[MSOE[string]] over a JSON array mixing plain + special.
	// Proves each slice element routes through protoMSOE.UnmarshalJSON (pointer
	// receiver) even though the element type is a generic type parameter.
	var nested protoVOV[protoMSOE[string]]
	if err := json.Unmarshal([]byte(`["a",{"specialValue":"Infinity"},"c"]`), &nested); err != nil {
		t.Fatalf("nested decode: %v", err)
	}
	if !nested.isMulti || len(nested.multiple) != 3 {
		t.Fatalf("nested shape: got %+v", nested)
	}
	if nested.multiple[0].value != "a" || nested.multiple[0].isSpecial {
		t.Fatalf("nested[0]: %+v", nested.multiple[0])
	}
	if !nested.multiple[1].isSpecial || nested.multiple[1].special != "Infinity" {
		t.Fatalf("nested[1] not dispatched to MSOE unmarshaler: %+v", nested.multiple[1])
	}
	if nested.multiple[2].value != "c" || nested.multiple[2].isSpecial {
		t.Fatalf("nested[2]: %+v", nested.multiple[2])
	}
}

// ---------------------------------------------------------------------------
// CRIT-2: Table[T,PT] pointer-constraint idiom — new(T), decode, call a
// pointer-receiver Model method, return PT.
// ---------------------------------------------------------------------------

type protoModel interface {
	setClient(c string)
	client() string
}

type protoRecord struct {
	Name *string `json:"fldName,omitempty"`
	cli  string
}

func (m *protoRecord) setClient(c string) { m.cli = c }
func (m *protoRecord) client() string     { return m.cli }

type protoTable[T any, PT interface {
	*T
	protoModel
}] struct {
	clientTag string
}

func (tbl protoTable[T, PT]) get(_ context.Context, raw string) (PT, error) {
	var v T
	pt := PT(&v)
	if err := json.Unmarshal([]byte(raw), pt); err != nil {
		return nil, err
	}
	pt.setClient(tbl.clientTag) // pointer-receiver Model method visible via constraint
	return pt, nil
}

func TestProtoPointerConstraintTable(t *testing.T) {
	tbl := protoTable[protoRecord, *protoRecord]{clientTag: "attached"}
	got, err := tbl.get(context.Background(), `{"fldName":"Widget"}`)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if got.Name == nil || *got.Name != "Widget" {
		t.Fatalf("decode into new(T) failed: %+v", got)
	}
	if got.client() != "attached" {
		t.Fatalf("setClient via constraint failed: %q", got.client())
	}
}

// ---------------------------------------------------------------------------
// CRIT (Duration): wire = numeric seconds, not nanoseconds / "PT30S".
// ---------------------------------------------------------------------------

type protoDuration time.Duration

func (d protoDuration) MarshalJSON() ([]byte, error) {
	secs := time.Duration(d).Seconds()
	return []byte(strconv.FormatFloat(secs, 'f', -1, 64)), nil
}

func (d *protoDuration) UnmarshalJSON(b []byte) error {
	secs, err := strconv.ParseFloat(string(bytes.TrimSpace(b)), 64)
	if err != nil {
		return err
	}
	*d = protoDuration(time.Duration(secs * float64(time.Second)))
	return nil
}

func TestProtoDurationSeconds(t *testing.T) {
	d := protoDuration(30 * time.Second)
	out, err := json.Marshal(d)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(out) != "30" {
		t.Fatalf("duration should encode as numeric seconds, got %q", out)
	}
	var back protoDuration
	if err := json.Unmarshal([]byte("90"), &back); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if time.Duration(back) != 90*time.Second {
		t.Fatalf("duration decode: got %v", time.Duration(back))
	}
}

// ---------------------------------------------------------------------------
// Date: 3-format decode (RFC3339-fractional, RFC3339, date-only -> midnight UTC).
// ---------------------------------------------------------------------------

type protoTime struct{ time.Time }

func (t *protoTime) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	for _, layout := range []string{time.RFC3339Nano, time.RFC3339, "2006-01-02"} {
		if parsed, err := time.Parse(layout, s); err == nil {
			t.Time = parsed.UTC()
			return nil
		}
	}
	return &time.ParseError{Value: s}
}

func TestProtoDate3Format(t *testing.T) {
	cases := map[string]string{
		`"2024-01-15T10:30:00.000Z"`: "2024-01-15T10:30:00Z",
		`"2024-01-15T10:30:00Z"`:     "2024-01-15T10:30:00Z",
		`"2024-01-15"`:               "2024-01-15T00:00:00Z",
	}
	for in, want := range cases {
		var pt protoTime
		if err := json.Unmarshal([]byte(in), &pt); err != nil {
			t.Fatalf("decode %s: %v", in, err)
		}
		if got := pt.Time.Format(time.RFC3339); got != want {
			t.Fatalf("decode %s: got %s want %s", in, got, want)
		}
	}
}

// ---------------------------------------------------------------------------
// Model decode + snapshot dirty tracking + writable-only payload.
// ---------------------------------------------------------------------------

func TestProtoSnapshotPayload(t *testing.T) {
	// Decode by field-ID json tags incl. a computed (pointer) field.
	type model struct {
		Writable *string `json:"fldW,omitempty"`
		Computed *string `json:"fldC,omitempty"` // read-only by convention
	}
	var m model
	if err := json.Unmarshal([]byte(`{"fldW":"x","fldC":"auto"}`), &m); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if m.Writable == nil || *m.Writable != "x" || m.Computed == nil || *m.Computed != "auto" {
		t.Fatalf("field-id decode failed: %+v", m)
	}

	// Writable-only payload (computed excluded), snapshot diff for dirty fields.
	snapshot := map[string]json.RawMessage{"fldW": json.RawMessage(`"x"`)}
	newVal, _ := json.Marshal(*m.Writable)
	dirty := map[string]json.RawMessage{}
	if !bytes.Equal(snapshot["fldW"], newVal) {
		dirty["fldW"] = newVal
	}
	if len(dirty) != 0 {
		t.Fatalf("clean field should not be dirty: %v", dirty)
	}
	updated := "y"
	m.Writable = &updated
	newVal, _ = json.Marshal(*m.Writable)
	if !bytes.Equal(snapshot["fldW"], newVal) {
		dirty["fldW"] = newVal
	}
	if len(dirty) != 1 {
		t.Fatalf("changed field should be dirty: %v", dirty)
	}
}
