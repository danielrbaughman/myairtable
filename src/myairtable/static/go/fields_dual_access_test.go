package airtable

// White-box tests for Fields dual ID/name access. Mirrors the Java
// TestFieldsDualAccess cases adapted to the Go API.

import (
	"encoding/json"
	"errors"
	"testing"
)

func newTestFields() *Fields {
	values := map[string]json.RawMessage{
		"fldName": json.RawMessage(`"Alice"`),
		"fldAge":  json.RawMessage(`42`),
	}
	nameToID := map[string]string{
		"Name": "fldName",
		"Age":  "fldAge",
	}
	return NewFields(values, nameToID)
}

func TestFieldsGetByID(t *testing.T) {
	f := newTestFields()
	var name string
	if err := f.Get("fldName", &name); err != nil {
		t.Fatalf("Get by ID: %v", err)
	}
	if name != "Alice" {
		t.Fatalf("name = %q, want Alice", name)
	}
}

func TestFieldsGetByName(t *testing.T) {
	f := newTestFields()
	var age float64
	if err := f.Get("Age", &age); err != nil {
		t.Fatalf("Get by name: %v", err)
	}
	if age != 42 {
		t.Fatalf("age = %v, want 42", age)
	}
}

func TestFieldsGetRawByIDAndName(t *testing.T) {
	f := newTestFields()
	raw, ok := f.GetRaw("fldName")
	if !ok {
		t.Fatalf("GetRaw by ID should be present")
	}
	if string(raw) != `"Alice"` {
		t.Fatalf("raw = %s", raw)
	}

	raw2, ok2 := f.GetRaw("Name")
	if !ok2 {
		t.Fatalf("GetRaw by name should be present")
	}
	if string(raw2) != `"Alice"` {
		t.Fatalf("raw2 = %s", raw2)
	}
}

func TestFieldsIDFirstPrecedence(t *testing.T) {
	// A key that is BOTH a valid field ID in values AND a name in nameToID must
	// resolve to the ID-keyed value first.
	values := map[string]json.RawMessage{
		"collision": json.RawMessage(`"by-id"`),
		"fldReal":   json.RawMessage(`"by-name"`),
	}
	nameToID := map[string]string{
		"collision": "fldReal", // name "collision" -> id "fldReal"
	}
	f := NewFields(values, nameToID)

	var got string
	if err := f.Get("collision", &got); err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got != "by-id" {
		t.Fatalf("ID-first precedence failed: got %q, want by-id", got)
	}
}

func TestFieldsGetMissingReturnsNotFound(t *testing.T) {
	f := newTestFields()
	var dst string
	err := f.Get("Nonexistent", &dst)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("missing field should return ErrNotFound, got %v", err)
	}
}

func TestFieldsGetRawMissing(t *testing.T) {
	f := newTestFields()
	if _, ok := f.GetRaw("Nope"); ok {
		t.Fatalf("missing field GetRaw should report not present")
	}
}

func TestFieldsSetByName(t *testing.T) {
	f := newTestFields()
	if err := f.Set("Name", "Bob"); err != nil {
		t.Fatalf("Set by name: %v", err)
	}
	// Set by name should write to the resolved ID slot.
	raw, ok := f.Raw()["fldName"]
	if !ok {
		t.Fatalf("Set by name should write to fldName")
	}
	if string(raw) != `"Bob"` {
		t.Fatalf("raw = %s, want \"Bob\"", raw)
	}
}

func TestFieldsSetByUnknownKeyUsesKeyAsID(t *testing.T) {
	f := newTestFields()
	if err := f.Set("fldNew", 7); err != nil {
		t.Fatalf("Set: %v", err)
	}
	var got float64
	if err := f.Get("fldNew", &got); err != nil {
		t.Fatalf("Get back: %v", err)
	}
	if got != 7 {
		t.Fatalf("got = %v, want 7", got)
	}
}

func TestNewFieldsNilValues(t *testing.T) {
	f := NewFields(nil, nil)
	if f.Raw() == nil {
		t.Fatalf("nil values should be initialized to empty map")
	}
	if err := f.Set("fldX", "y"); err != nil {
		t.Fatalf("Set on nil-initialized Fields: %v", err)
	}
}
