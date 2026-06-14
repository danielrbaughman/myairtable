package airtable

// G11.2 — DX-surface tests. Mirrors the intent of Java TestDxHelpers
// (MaybeSpecialOrError value access, VecOrValue cleanValues, view-id sugar, and
// the pointer-helper constructors) adapted to the Go API. White-box (package
// airtable) so it can exercise package-internal helpers; all offline.

import (
	"encoding/json"
	"testing"
	"time"
)

// testView is a local stand-in for a generated {Table}View constant — it
// implements the View interface so Query.WithView can be exercised without
// importing generated code (static tests can't).
type testView string

func (v testView) ViewID() string { return string(v) }

// --- MaybeSpecialOrError accessor surface ---

func TestDxMSOEValueAccess(t *testing.T) {
	var present MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`2.5`), &present); err != nil {
		t.Fatalf("unmarshal value: %v", err)
	}
	if v, ok := present.Value(); !ok || v != 2.5 {
		t.Fatalf("Value() = %v,%v want 2.5,true", v, ok)
	}
	if present.IsSpecial() || present.IsError() {
		t.Fatal("plain value is neither special nor error")
	}

	var special MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`{"specialValue":"NaN"}`), &special); err != nil {
		t.Fatalf("unmarshal special: %v", err)
	}
	if _, ok := special.Value(); ok {
		t.Fatal("special must not report a present Value()")
	}
	if !special.IsSpecial() || special.Special() == nil || special.Special().SpecialValue != "NaN" {
		t.Fatalf("Special() = %+v, want NaN", special.Special())
	}

	var errVal MaybeSpecialOrError[float64]
	if err := json.Unmarshal([]byte(`{"error":"#ERROR!"}`), &errVal); err != nil {
		t.Fatalf("unmarshal error: %v", err)
	}
	if _, ok := errVal.Value(); ok {
		t.Fatal("error must not report a present Value()")
	}
	if !errVal.IsError() || errVal.ErrorVal() == nil || errVal.ErrorVal().Error != "#ERROR!" {
		t.Fatalf("ErrorVal() = %+v, want #ERROR!", errVal.ErrorVal())
	}
}

// --- VecOrValue.Values ---

func TestDxVecOrValueValues(t *testing.T) {
	var single VecOrValue[string]
	if err := json.Unmarshal([]byte(`"solo"`), &single); err != nil {
		t.Fatalf("unmarshal single: %v", err)
	}
	if got := single.Values(); len(got) != 1 || got[0] != "solo" {
		t.Fatalf("single Values() = %v, want [solo]", got)
	}

	var multi VecOrValue[string]
	if err := json.Unmarshal([]byte(`["a","b"]`), &multi); err != nil {
		t.Fatalf("unmarshal multi: %v", err)
	}
	if got := multi.Values(); len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("multi Values() = %v, want [a b]", got)
	}
}

// --- CleanValues over a nested VecOrValue[MaybeSpecialOrError[T]] ---

func TestDxCleanValuesSingleShape(t *testing.T) {
	var v VecOrValue[MaybeSpecialOrError[float64]]
	if err := json.Unmarshal([]byte(`1.0`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	got := CleanValues(v)
	if len(got) != 1 || got[0] != 1.0 {
		t.Fatalf("CleanValues single = %v, want [1]", got)
	}
}

func TestDxCleanValuesSingleSentinelCollapsesToEmpty(t *testing.T) {
	var v VecOrValue[MaybeSpecialOrError[float64]]
	if err := json.Unmarshal([]byte(`{"error":"#ERROR!"}`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got := CleanValues(v); len(got) != 0 {
		t.Fatalf("single error sentinel should clean to empty, got %v", got)
	}
}

func TestDxCleanValuesDropsSpecialsErrorsAndNulls(t *testing.T) {
	var v VecOrValue[MaybeSpecialOrError[float64]]
	// A list mixing plain values, a null element, a special, and an error.
	if err := json.Unmarshal([]byte(`[1.0,null,{"specialValue":"NaN"},2.0,{"error":"#ERROR!"}]`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	got := CleanValues(v)
	if len(got) != 2 || got[0] != 1.0 || got[1] != 2.0 {
		t.Fatalf("CleanValues = %v, want [1 2]", got)
	}
}

func TestDxCleanValuesAllPresentRoundTrip(t *testing.T) {
	var v VecOrValue[MaybeSpecialOrError[string]]
	if err := json.Unmarshal([]byte(`["a","b"]`), &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	got := CleanValues(v)
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("CleanValues = %v, want [a b]", got)
	}
}

// --- pointer-helper constructors ---

func TestDxPointerHelpers(t *testing.T) {
	if got := String("x"); got == nil || *got != "x" {
		t.Fatalf("String() = %v, want *\"x\"", got)
	}
	if got := Float64(2.5); got == nil || *got != 2.5 {
		t.Fatalf("Float64() = %v, want *2.5", got)
	}
	if got := Int64(7); got == nil || *got != 7 {
		t.Fatalf("Int64() = %v, want *7", got)
	}
	if got := Bool(true); got == nil || *got != true {
		t.Fatalf("Bool() = %v, want *true", got)
	}

	ts := time.Date(2024, 1, 2, 3, 4, 5, 0, time.UTC)
	if got := Time(ts); got == nil || !got.Time.Equal(ts) {
		t.Fatalf("Time() = %v, want wrapping %v", got, ts)
	}

	d := 90 * time.Minute
	if got := Duration(d); got == nil || time.Duration(*got) != d {
		t.Fatalf("Duration() = %v, want wrapping %v", got, d)
	}
}

// --- View.ViewID via Query.WithView ---

func TestDxQueryWithView(t *testing.T) {
	q := (&Query{}).WithView(testView("viwSTUB12345"))
	if q.View != "viwSTUB12345" {
		t.Fatalf("WithView set View = %q, want viwSTUB12345", q.View)
	}
	// The encoded view id must land in the rendered query parameters.
	if got := q.toValues("").Get("view"); got != "viwSTUB12345" {
		t.Fatalf("rendered view param = %q, want viwSTUB12345", got)
	}
	// A later WithView overrides an earlier one.
	q2 := (&Query{View: "viwOLD"}).WithView(testView("viwNEW"))
	if q2.View != "viwNEW" {
		t.Fatalf("WithView override = %q, want viwNEW", q2.View)
	}
}
