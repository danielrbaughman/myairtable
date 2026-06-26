package airtable

// Deterministic / hermetic tests for the idempotency-aware retry policy in
// Client.do (epic follow-up myairtable-rxht, T1). The live retry/transient
// behavior is otherwise only exercised against the real API; here we install a
// scripted http.RoundTripper (via the unexported setHTTPClient seam) that counts
// attempts and returns canned responses, so the policy is pinned without any
// network, sleeps, or flakiness.
//
// Policy under test (see Client.do):
//   - 429              -> ALWAYS retried, then *RateLimitError after maxRetries.
//   - 5xx              -> retried ONLY IF idempotent.
//   - transport error  -> retried ONLY IF idempotent.
//   - createRecords    -> POST, non-idempotent -> 5xx is NOT retried (1 attempt).
//
// Retry delays are shrunk to ~microseconds for the duration of each test (the
// retryBaseDelay/maxRetryWait knobs are package vars precisely so tests need not
// sleep ~1s per retry); production defaults are restored on cleanup and are
// never mutated by NewClient.

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// scriptedRoundTripper returns canned responses (or transport errors) in order,
// counting every RoundTrip call. Once the script is exhausted it repeats the
// final entry, so a "persistent 5xx" test only needs one scripted 503.
type scriptedRoundTripper struct {
	steps    []scriptStep
	attempts int32
}

type scriptStep struct {
	status int // HTTP status to return (ignored if err != nil)
	body   string
	err    error // if non-nil, simulate a transport/IO failure
}

func (s *scriptedRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	i := int(atomic.AddInt32(&s.attempts, 1)) - 1
	step := s.steps[len(s.steps)-1]
	if i < len(s.steps) {
		step = s.steps[i]
	}
	if step.err != nil {
		return nil, step.err
	}
	return &http.Response{
		StatusCode: step.status,
		Body:       io.NopCloser(strings.NewReader(step.body)),
		Header:     make(http.Header),
		Request:    req,
	}, nil
}

func (s *scriptedRoundTripper) count() int { return int(atomic.LoadInt32(&s.attempts)) }

// newScriptedClient builds a Client wired to the scripted RoundTripper. The
// apiKey/baseID are non-empty so do() does not short-circuit on credentials;
// the URL is irrelevant because the RoundTripper intercepts every request.
func newScriptedClient(rt http.RoundTripper) *Client {
	c := NewClient("test-key", "appTEST", 0)
	c.setHTTPClient(&http.Client{Transport: rt})
	return c
}

// shrinkRetryDelays makes retries effectively instant for the test and restores
// the production defaults afterward.
func shrinkRetryDelays(t *testing.T) {
	t.Helper()
	origBase, origMax := retryBaseDelay, maxRetryWait
	retryBaseDelay = time.Microsecond
	maxRetryWait = time.Microsecond
	t.Cleanup(func() {
		retryBaseDelay = origBase
		maxRetryWait = origMax
	})
}

// 1. Idempotent GET: 503, 503, 200 -> 3 attempts, success.
func TestRetryHermetic_Idempotent5xxThenSuccess(t *testing.T) {
	shrinkRetryDelays(t)
	rt := &scriptedRoundTripper{steps: []scriptStep{
		{status: 503, body: `{"error":"SERVICE_UNAVAILABLE"}`},
		{status: 503, body: `{"error":"SERVICE_UNAVAILABLE"}`},
		{status: 200, body: `{"id":"rec1","fields":{}}`},
	}}
	c := newScriptedClient(rt)

	body, err := c.do(context.Background(), http.MethodGet, "https://api.airtable.com/v0/appTEST/tbl/rec1", nil, true)
	if err != nil {
		t.Fatalf("expected success after 2 retries, got error: %v", err)
	}
	if got := string(body); got != `{"id":"rec1","fields":{}}` {
		t.Fatalf("unexpected body: %s", got)
	}
	if n := rt.count(); n != 3 {
		t.Fatalf("expected exactly 3 attempts (503,503,200), got %d", n)
	}
}

// 2. Idempotent op, persistent 503 -> maxRetries+1 attempts, then an error.
func TestRetryHermetic_IdempotentPersistent5xxExhausts(t *testing.T) {
	shrinkRetryDelays(t)
	rt := &scriptedRoundTripper{steps: []scriptStep{
		{status: 503, body: `{"error":{"type":"SERVICE_UNAVAILABLE","message":"down"}}`},
	}}
	c := newScriptedClient(rt)

	_, err := c.do(context.Background(), http.MethodGet, "https://api.airtable.com/v0/appTEST/tbl", nil, true)
	if err == nil {
		t.Fatal("expected an error after exhausting retries on persistent 503")
	}
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != 503 {
		t.Fatalf("expected *APIError{StatusCode:503}, got %T: %v", err, err)
	}
	if want, n := maxRetries+1, rt.count(); n != want {
		t.Fatalf("expected exactly maxRetries+1 = %d attempts, got %d", want, n)
	}
}

// 3. NON-idempotent createRecords on 503 -> exactly 1 attempt (no retry).
func TestRetryHermetic_NonIdempotentCreate5xxNoRetry(t *testing.T) {
	shrinkRetryDelays(t)
	rt := &scriptedRoundTripper{steps: []scriptStep{
		{status: 503, body: `{"error":{"type":"SERVICE_UNAVAILABLE","message":"down"}}`},
	}}
	c := newScriptedClient(rt)

	_, err := c.createRecords(context.Background(), "tbl", []map[string]json.RawMessage{{}}, false)
	if err == nil {
		t.Fatal("expected an error from createRecords on 503")
	}
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != 503 {
		t.Fatalf("expected *APIError{StatusCode:503}, got %T: %v", err, err)
	}
	if n := rt.count(); n != 1 {
		t.Fatalf("non-idempotent POST must NOT retry on 5xx: expected exactly 1 attempt, got %d", n)
	}
}

// 4. 429 then 200 -> retried (429 is always transient, regardless of idempotency).
func TestRetryHermetic_429ThenSuccess(t *testing.T) {
	shrinkRetryDelays(t)
	rt := &scriptedRoundTripper{steps: []scriptStep{
		{status: 429, body: `{"error":"RATE_LIMITED"}`},
		{status: 200, body: `{"id":"rec1","fields":{}}`},
	}}
	c := newScriptedClient(rt)

	// Use a non-idempotent op to prove 429 is retried *even when* idempotent=false.
	_, err := c.createRecords(context.Background(), "tbl", []map[string]json.RawMessage{{}}, false)
	if err != nil {
		t.Fatalf("expected success after a 429 retry, got error: %v", err)
	}
	if n := rt.count(); n != 2 {
		t.Fatalf("expected exactly 2 attempts (429,200), got %d", n)
	}
}

// Bonus pin: a non-idempotent transport error is surfaced immediately (1 attempt),
// while an idempotent transport error is retried. Tightens the parity contract.
func TestRetryHermetic_TransportErrorIdempotencyGate(t *testing.T) {
	shrinkRetryDelays(t)
	transportErr := errors.New("dial tcp: connection refused")

	t.Run("NonIdempotentNoRetry", func(t *testing.T) {
		rt := &scriptedRoundTripper{steps: []scriptStep{{err: transportErr}}}
		c := newScriptedClient(rt)
		_, err := c.do(context.Background(), http.MethodPost, "https://api.airtable.com/v0/appTEST/tbl", []byte(`{}`), false)
		if err == nil {
			t.Fatal("expected the transport error to surface")
		}
		if n := rt.count(); n != 1 {
			t.Fatalf("non-idempotent transport error must NOT retry: expected 1 attempt, got %d", n)
		}
	})

	t.Run("IdempotentRetriesThenSucceeds", func(t *testing.T) {
		rt := &scriptedRoundTripper{steps: []scriptStep{
			{err: transportErr},
			{status: 200, body: `{"id":"rec1","fields":{}}`},
		}}
		c := newScriptedClient(rt)
		_, err := c.do(context.Background(), http.MethodGet, "https://api.airtable.com/v0/appTEST/tbl", nil, true)
		if err != nil {
			t.Fatalf("expected success after retrying transport error, got %v", err)
		}
		if n := rt.count(); n != 2 {
			t.Fatalf("expected 2 attempts (err, 200), got %d", n)
		}
	})
}
