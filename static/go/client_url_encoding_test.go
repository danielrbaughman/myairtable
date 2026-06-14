package airtable

// White-box tests for Client.recordURL. Mirrors the Java TestClientUrlEncoding
// cases adapted to the Go API. Critically, asserts that '+' inside a formula is
// percent-encoded as %2B (not left raw), so formulas round-trip through Airtable.

import (
	"net/url"
	"strings"
	"testing"
)

func TestRecordURLBasePath(t *testing.T) {
	c := NewClient("k", "appXXX", 0)
	got := c.recordURL("tblYYY", "", nil)
	want := "https://api.airtable.com/v0/appXXX/tblYYY"
	if got != want {
		t.Fatalf("recordURL = %q, want %q", got, want)
	}
}

func TestRecordURLWithRecordID(t *testing.T) {
	c := NewClient("k", "appXXX", 0)
	got := c.recordURL("tblYYY", "recZZZ", nil)
	want := "https://api.airtable.com/v0/appXXX/tblYYY/recZZZ"
	if got != want {
		t.Fatalf("recordURL = %q, want %q", got, want)
	}
}

func TestRecordURLPercentEncodesPlusInFormula(t *testing.T) {
	c := NewClient("k", "appXXX", 0)
	q := (&Query{}).WithFilter("LEN({Primary Key})+1")
	got := c.recordURL("tblYYY", "", q.toValues(""))

	// The '+' must be percent-encoded as %2B, NOT left raw (raw '+' would decode
	// to a space on Airtable's side and corrupt the formula).
	if !strings.Contains(got, "%2B1") {
		t.Fatalf("expected '+' encoded as %%2B in URL, got %q", got)
	}
	// A literal "+1" (raw plus) must not appear.
	if strings.Contains(got, "Key%7D+1") || strings.Contains(got, "Key}+1") {
		t.Fatalf("'+' must not be left raw, got %q", got)
	}

	// And the whole thing must parse back to the original formula.
	idx := strings.Index(got, "?")
	if idx < 0 {
		t.Fatalf("expected a query string, got %q", got)
	}
	parsed, err := url.ParseQuery(got[idx+1:])
	if err != nil {
		t.Fatalf("query string did not parse: %v", err)
	}
	if f := parsed.Get("filterByFormula"); f != "LEN({Primary Key})+1" {
		t.Fatalf("filterByFormula round-trip = %q, want %q", f, "LEN({Primary Key})+1")
	}
}

func TestRecordURLEncodesSpaces(t *testing.T) {
	c := NewClient("k", "appXXX", 0)
	q := (&Query{}).WithFilter("{Primary Key}")
	got := c.recordURL("tblYYY", "", q.toValues(""))
	// url.Values.Encode renders spaces as '+'. Confirm the space is not left raw.
	if strings.Contains(got, "Primary Key") {
		t.Fatalf("raw space should not appear in URL, got %q", got)
	}
}

func TestRecordURLEscapesPathSegments(t *testing.T) {
	c := NewClient("k", "app/With Space", 0)
	got := c.recordURL("tbl/Weird Name", "rec With Space", nil)
	// Path segments use url.PathEscape: spaces -> %20, '/' -> %2F.
	if strings.Contains(got, " ") {
		t.Fatalf("raw space in path, got %q", got)
	}
	if !strings.Contains(got, "app%2FWith%20Space") {
		t.Fatalf("base ID not path-escaped, got %q", got)
	}
	if !strings.Contains(got, "tbl%2FWeird%20Name") {
		t.Fatalf("table not path-escaped, got %q", got)
	}
	if !strings.Contains(got, "rec%20With%20Space") {
		t.Fatalf("record not path-escaped, got %q", got)
	}
}

func TestRecordURLNoQueryWhenEmpty(t *testing.T) {
	c := NewClient("k", "appXXX", 0)
	got := c.recordURL("tblYYY", "recZZZ", url.Values{})
	if strings.Contains(got, "?") {
		t.Fatalf("empty query should not add '?', got %q", got)
	}
}
