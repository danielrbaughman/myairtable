package airtable

// White-box tests for the formula runtime coercions: N, S, IsTruthy, A, AN, AS.
// Mirrors the Java TestValueCoercion cases adapted to the Go API.

import (
	"reflect"
	"testing"
)

func TestNCoercion(t *testing.T) {
	cases := []struct {
		in   any
		want float64
	}{
		{nil, 0},
		{true, 1},
		{false, 0},
		{float64(3.5), 3.5},
		{int64(7), 7},
		{int(9), 9},
		{"42", 42},
		{"  42.5  ", 42.5},
		{"notanum", 0},
		{[]any{float64(5), float64(6)}, 5}, // first element
		{[]any{}, 0},
		{map[string]any{}, 0}, // unsupported -> 0
	}
	for _, c := range cases {
		if got := N(c.in); got != c.want {
			t.Errorf("N(%#v) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestSCoercion(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{nil, ""},
		{"hi", "hi"},
		{true, "1"},
		{false, "0"}, // note: false -> "0"
		{float64(42), "42"},
		{float64(42.0), "42"},   // integral float drops decimal
		{float64(3.14), "3.14"}, // fractional kept
		{int64(8), "8"},
		{int(9), "9"},
		{[]any{"first", "second"}, "first, second"}, // multi-value joins with ", "
		{[]any{}, ""},
		{map[string]any{}, ""},
	}
	for _, c := range cases {
		if got := S(c.in); got != c.want {
			t.Errorf("S(%#v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestIsTruthy(t *testing.T) {
	cases := []struct {
		in   any
		want bool
	}{
		{nil, false},
		{"", false},
		{"x", true},
		{true, true},
		{false, false},
		{float64(0), false},
		{float64(1), true},
		{int64(0), false},
		{int64(3), true},
		{int(0), false},
		{[]any{}, false},
		{[]any{1}, true},
		{map[string]any{}, false},
		{map[string]any{"a": 1}, true},
	}
	for _, c := range cases {
		if got := IsTruthy(c.in); got != c.want {
			t.Errorf("IsTruthy(%#v) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestIsTruthyNaN(t *testing.T) {
	nan := 0.0
	nan = nan / nan
	if IsTruthy(nan) {
		t.Fatalf("NaN should not be truthy")
	}
}

func TestAFlattening(t *testing.T) {
	got := A("a", nil, []any{"b", "c"}, float64(4))
	want := []any{"a", "b", "c", float64(4)}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("A(...) = %#v, want %#v", got, want)
	}
}

func TestAEmpty(t *testing.T) {
	got := A()
	if len(got) != 0 {
		t.Fatalf("A() should be empty, got %#v", got)
	}
}

func TestANFlattenAndCoerce(t *testing.T) {
	got := AN("1", nil, []any{float64(2), "3"}, true)
	want := []float64{1, 2, 3, 1}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("AN(...) = %#v, want %#v", got, want)
	}
}

func TestASFlattenAndCoerce(t *testing.T) {
	got := AS(float64(1), nil, []any{false, "x"})
	want := []string{"1", "0", "x"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("AS(...) = %#v, want %#v", got, want)
	}
}
