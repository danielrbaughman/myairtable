package airtable

// Regression tests for the ultra-review fixes:
//   H1 — numeric filter formatting must not use scientific notation (>= 1e6).
//   M1 — transient 5xx are retried (and non-retryable 4xx are not).
//   M2 — CreateMany/UpdateMany return the same hydrated input models.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

// ---- PR review: V() unwraps wrapper types (doc accuracy + duration arithmetic) ----

func TestVUnwrapsWrapperTypes(t *testing.T) {
	when := time.Date(2024, 1, 2, 3, 4, 5, 0, time.UTC)
	at := AirtableTime{Time: when}
	if got := V(at); got != when {
		t.Errorf("V(AirtableTime) = %v, want %v", got, when)
	}
	if got := V(&at); got != when {
		t.Errorf("V(*AirtableTime) = %v, want %v", got, when)
	}
	dur := AirtableDuration(90 * time.Second)
	if got := V(dur); got != 90.0 {
		t.Errorf("V(AirtableDuration) = %v, want 90 (seconds)", got)
	}
	if got := V(&dur); got != 90.0 {
		t.Errorf("V(*AirtableDuration) = %v, want 90 (seconds)", got)
	}
	// nil wrapper pointers box to nil.
	var nilTime *AirtableTime
	if got := V(nilTime); got != nil {
		t.Errorf("V(nil *AirtableTime) = %v, want nil", got)
	}
	// Scalars still pass through.
	if got := V(String("x")); got != "x" {
		t.Errorf("V(*string) = %v, want x", got)
	}
	// Duration boxed by V is now coercible by N (was 0 before the fix).
	if got := N(V(dur)); got != 90.0 {
		t.Errorf("N(V(duration)) = %v, want 90", got)
	}
}

// ---- H1: number formatting -------------------------------------------------

func TestNumberFilterNoScientificNotation(t *testing.T) {
	f := NewNumberField("Amount")
	cases := []struct {
		got  Formula
		want string
	}{
		{f.Eq(1000000), "{Amount}=1000000"},
		{f.Eq(10000000), "{Amount}=10000000"},
		{f.Eq(1234567.89), "{Amount}=1234567.89"},
		{f.GreaterThan(1e12), "{Amount}>1000000000000"},
		{f.Eq(42), "{Amount}=42"},
		{f.Eq(0.5), "{Amount}=0.5"},
	}
	for _, c := range cases {
		if got := c.got.String(); got != c.want {
			t.Errorf("got %q, want %q", got, c.want)
		}
	}
}

// ---- M1: retry on 5xx, not on other 4xx ------------------------------------

type flakyTransport struct {
	failStatus int // status returned for the first `failures` calls
	failures   int
	calls      int
}

func (rt *flakyTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	rt.calls++
	if rt.calls <= rt.failures {
		return &http.Response{
			StatusCode: rt.failStatus,
			Header:     http.Header{},
			Body:       io.NopCloser(strings.NewReader(`{"error":{"type":"X","message":"boom"}}`)),
		}, nil
	}
	return cannedResponse(`{"id":"recX","fields":{}}`), nil
}

func withFastRetries(t *testing.T) {
	t.Helper()
	old := retryBaseDelay
	retryBaseDelay = time.Millisecond
	t.Cleanup(func() { retryBaseDelay = old })
}

func TestRetriesOnTransient5xx(t *testing.T) {
	withFastRetries(t)
	rt := &flakyTransport{failStatus: 503, failures: 2}
	c := clientWithTransport(rt)
	if _, err := c.getRecord(context.Background(), "tblRev", "recX"); err != nil {
		t.Fatalf("expected success after retrying 5xx, got %v", err)
	}
	if rt.calls != 3 {
		t.Fatalf("expected 3 calls (2x503 + 1x200), got %d", rt.calls)
	}
}

func TestDoesNotRetryNonRetryable4xx(t *testing.T) {
	withFastRetries(t)
	rt := &flakyTransport{failStatus: 422, failures: 99}
	c := clientWithTransport(rt)
	_, err := c.getRecord(context.Background(), "tblRev", "recX")
	if err == nil {
		t.Fatal("expected an error for 422")
	}
	if rt.calls != 1 {
		t.Fatalf("422 must not be retried: expected 1 call, got %d", rt.calls)
	}
}

// ---- M2: CreateMany/UpdateMany return hydrated inputs -----------------------

type revModel struct {
	Name        *string `json:"fldName,omitempty"`
	id          string
	createdTime *AirtableTime
	client      *Client
	snapshot    map[string]json.RawMessage
}

func (m *revModel) TableID() string { return "tblRev" }
func (m *revModel) ID() string      { return m.id }
func (m *revModel) writableFields() map[string]json.RawMessage {
	return map[string]json.RawMessage{"fldName": mustMarshal(m.Name)}
}
func (m *revModel) setID(id string)                            { m.id = id }
func (m *revModel) setCreatedTime(t *AirtableTime)             { m.createdTime = t }
func (m *revModel) setClient(c *Client)                        { m.client = c }
func (m *revModel) getClient() *Client                         { return m.client }
func (m *revModel) setSnapshot(s map[string]json.RawMessage)   { m.snapshot = s }
func (m *revModel) snapshotFields() map[string]json.RawMessage { return m.snapshot }

func TestCreateManyReturnsHydratedInputs(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewTable[revModel, *revModel](clientWithTransport(rt), "tblRev", nil)
	m1 := &revModel{Name: String("a")}
	m2 := &revModel{Name: String("b")}

	out, err := tbl.CreateMany(context.Background(), []*revModel{m1, m2})
	if err != nil {
		t.Fatalf("CreateMany: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("expected 2 results, got %d", len(out))
	}
	// Returned objects must BE the inputs (same pointers), hydrated in place.
	if out[0] != m1 || out[1] != m2 {
		t.Fatal("CreateMany must return the same input objects, not fresh copies")
	}
	if m1.ID() == "" || m2.ID() == "" {
		t.Fatal("inputs were not hydrated with server IDs")
	}
}
