package airtable

// White-box tests for MaybeSpecialOrError[T] and VecOrValue[T]. Mirrors the Java
// TestSpecialErrorDecoding cases adapted to the Go API.

import (
	"encoding/json"
	"testing"
)

func TestMSOEPlainValueFloat(t *testing.T) {
	var m MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`3.14`), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	v, ok := m.Value()
	if !ok {
		t.Fatalf("expected hasValue true")
	}
	if v != 3.14 {
		t.Fatalf("value = %v, want 3.14", v)
	}
	if m.IsSpecial() || m.IsError() {
		t.Fatalf("plain value should be neither special nor error")
	}
}

func TestMSOEPlainValueString(t *testing.T) {
	var m MaybeSpecialOrError[string]
	if err := json.Unmarshal([]byte(`"hello"`), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	v, ok := m.Value()
	if !ok || v != "hello" {
		t.Fatalf("value = %q ok=%v, want hello/true", v, ok)
	}
}

func TestMSOESpecialNumber(t *testing.T) {
	var m MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`{"specialValue":"NaN"}`), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !m.IsSpecial() {
		t.Fatalf("expected IsSpecial true")
	}
	if m.Special() == nil || m.Special().SpecialValue != "NaN" {
		t.Fatalf("special = %+v, want NaN", m.Special())
	}
	if _, ok := m.Value(); ok {
		t.Fatalf("special value should not have a plain value")
	}
}

func TestMSOEError(t *testing.T) {
	var m MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`{"error":"#ERROR!"}`), &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !m.IsError() {
		t.Fatalf("expected IsError true")
	}
	if m.ErrorVal() == nil || m.ErrorVal().Error != "#ERROR!" {
		t.Fatalf("errValue = %+v, want #ERROR!", m.ErrorVal())
	}
}

func TestMSOEEncodeRoundTrip(t *testing.T) {
	cases := []string{`2.5`, `{"specialValue":"Infinity"}`, `{"error":"#ERROR!"}`}
	for _, in := range cases {
		var m MaybeSpecialOrError[float64]
		if err := json.Unmarshal([]byte(in), &m); err != nil {
			t.Fatalf("unmarshal %s: %v", in, err)
		}
		out, err := json.Marshal(m)
		if err != nil {
			t.Fatalf("marshal %s: %v", in, err)
		}
		if string(out) != in {
			t.Fatalf("round trip: in=%s out=%s", in, out)
		}
	}
}

func TestMSOEEncodeEmptyIsNull(t *testing.T) {
	var m MaybeSpecialOrError[float64]
	out, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(out) != "null" {
		t.Fatalf("empty MSOE should marshal to null, got %s", out)
	}
}

func TestVecOrValueSingle(t *testing.T) {
	var v VecOrValue[string]
	if err := json.Unmarshal([]byte(`"solo"`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if v.IsMultiple {
		t.Fatalf("single value should not be multiple")
	}
	if v.Single != "solo" {
		t.Fatalf("single = %q, want solo", v.Single)
	}
	got := v.Values()
	if len(got) != 1 || got[0] != "solo" {
		t.Fatalf("Values() = %v, want [solo]", got)
	}
}

func TestVecOrValueArray(t *testing.T) {
	var v VecOrValue[string]
	if err := json.Unmarshal([]byte(`["a","b","c"]`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !v.IsMultiple {
		t.Fatalf("array value should be multiple")
	}
	got := v.Values()
	if len(got) != 3 || got[0] != "a" || got[2] != "c" {
		t.Fatalf("Values() = %v, want [a b c]", got)
	}
}

func TestVecOrValueMarshalRoundTrip(t *testing.T) {
	for _, in := range []string{`"x"`, `["x","y"]`} {
		var v VecOrValue[string]
		if err := json.Unmarshal([]byte(in), &v); err != nil {
			t.Fatalf("unmarshal %s: %v", in, err)
		}
		out, err := json.Marshal(v)
		if err != nil {
			t.Fatalf("marshal %s: %v", in, err)
		}
		if string(out) != in {
			t.Fatalf("round trip: in=%s out=%s", in, out)
		}
	}
}

func TestVecOrValueNestedMSOE(t *testing.T) {
	// CRIT-4: nested generic decode VecOrValue[MaybeSpecialOrError[string]].
	var v VecOrValue[MaybeSpecialOrError[string]]
	in := `["ok",{"error":"#ERROR!"},{"specialValue":"NaN"}]`
	if err := json.Unmarshal([]byte(in), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	vals := v.Values()
	if len(vals) != 3 {
		t.Fatalf("expected 3 values, got %d", len(vals))
	}
	if s, ok := vals[0].Value(); !ok || s != "ok" {
		t.Fatalf("vals[0] = %q ok=%v, want ok/true", s, ok)
	}
	if !vals[1].IsError() {
		t.Fatalf("vals[1] should be error")
	}
	if !vals[2].IsSpecial() {
		t.Fatalf("vals[2] should be special")
	}
}
