package airtable

// G11.2 — Bounded / batched table-op tests, ported OFFLINE from the intent of
// Java TestTableBoundedOps (chunk-of-10 fan-out + empty-input no-op). Go's
// client splits create/update/delete into chunks of `maxBatch` (10); these
// white-box tests pin that the wire batching matches the chunk bound and that
// empty input never touches the network.
//
// The client's *http.Client field is package-internal, so we inject a mock
// RoundTripper to count requests and records-per-request without any live calls.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

// recordingTransport captures each request and replies with a canned 200 that
// echoes back N records (one per record in the request body, with synthetic IDs)
// so the create/update decode paths succeed.
type recordingTransport struct {
	requests   []*http.Request
	bodyCounts []int // number of "records" in each request body (POST/PATCH)
	deletes    []int // number of "records[]" ids per DELETE
}

func (rt *recordingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	rt.requests = append(rt.requests, req)

	var respRecords []map[string]any
	switch req.Method {
	case http.MethodDelete:
		ids := req.URL.Query()["records[]"]
		rt.deletes = append(rt.deletes, len(ids))
		body := `{"records":[]}`
		return cannedResponse(body), nil
	case http.MethodPost, http.MethodPatch:
		var parsed struct {
			Records []json.RawMessage `json:"records"`
		}
		if req.Body != nil {
			raw, _ := io.ReadAll(req.Body)
			_ = json.Unmarshal(raw, &parsed)
		}
		rt.bodyCounts = append(rt.bodyCounts, len(parsed.Records))
		for i := range parsed.Records {
			respRecords = append(respRecords, map[string]any{
				"id":     "rec" + strings.Repeat("X", i+1),
				"fields": map[string]any{},
			})
		}
		out, _ := json.Marshal(map[string]any{"records": respRecords})
		return cannedResponse(string(out)), nil
	default:
		return cannedResponse(`{"records":[]}`), nil
	}
}

func cannedResponse(body string) *http.Response {
	return &http.Response{
		StatusCode: 200,
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(strings.NewReader(body)),
	}
}

func clientWithTransport(rt http.RoundTripper) *Client {
	c := NewClient("key", "appXXX", 0)
	c.httpClient = &http.Client{Transport: rt}
	return c
}

func makeFields(n int) []*Fields {
	out := make([]*Fields, 0, n)
	for i := 0; i < n; i++ {
		out = append(out, NewFields(map[string]json.RawMessage{"fldA": json.RawMessage(`"v"`)}, nil))
	}
	return out
}

// --- chunk-of-10 batching ---

func TestBoundedCreateBatchesInChunksOfTen(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)

	// 23 records => 3 POSTs of 10, 10, 3.
	if _, err := tbl.CreateMany(context.Background(), makeFields(23)); err != nil {
		t.Fatalf("CreateMany: %v", err)
	}
	if len(rt.requests) != 3 {
		t.Fatalf("expected 3 POST batches, got %d", len(rt.requests))
	}
	want := []int{maxBatch, maxBatch, 3}
	for i, w := range want {
		if rt.bodyCounts[i] != w {
			t.Fatalf("batch %d size = %d, want %d", i, rt.bodyCounts[i], w)
		}
	}
}

func TestBoundedCreateExactlyTenIsOneBatch(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
	if _, err := tbl.CreateMany(context.Background(), makeFields(maxBatch)); err != nil {
		t.Fatalf("CreateMany: %v", err)
	}
	if len(rt.requests) != 1 || rt.bodyCounts[0] != maxBatch {
		t.Fatalf("10 records should be one full batch, got %d requests %v", len(rt.requests), rt.bodyCounts)
	}
}

func TestBoundedDeleteBatchesInChunksOfTen(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)

	ids := make([]string, 0, 25)
	for i := 0; i < 25; i++ {
		ids = append(ids, "rec"+string(rune('a'+i)))
	}
	if err := tbl.DeleteMany(context.Background(), ids); err != nil {
		t.Fatalf("DeleteMany: %v", err)
	}
	if len(rt.requests) != 3 {
		t.Fatalf("expected 3 DELETE batches, got %d", len(rt.requests))
	}
	want := []int{maxBatch, maxBatch, 5}
	for i, w := range want {
		if rt.deletes[i] != w {
			t.Fatalf("delete batch %d size = %d, want %d", i, rt.deletes[i], w)
		}
	}
}

// --- empty-input no-op (no request hits the wire) ---

func TestBoundedCreateEmptyMakesNoRequests(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
	created, err := tbl.CreateMany(context.Background(), nil)
	if err != nil {
		t.Fatalf("empty CreateMany should not error: %v", err)
	}
	if len(created) != 0 {
		t.Fatalf("empty CreateMany returned %d records, want 0", len(created))
	}
	if len(rt.requests) != 0 {
		t.Fatalf("empty CreateMany must make no requests, made %d", len(rt.requests))
	}
}

func TestBoundedDeleteEmptyMakesNoRequests(t *testing.T) {
	rt := &recordingTransport{}
	tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
	if err := tbl.DeleteMany(context.Background(), nil); err != nil {
		t.Fatalf("empty DeleteMany should not error: %v", err)
	}
	if len(rt.requests) != 0 {
		t.Fatalf("empty DeleteMany must make no requests, made %d", len(rt.requests))
	}
}

func TestBoundedUpdateEmptyMakesNoRequests(t *testing.T) {
	rt := &recordingTransport{}
	c := clientWithTransport(rt)
	// updateRecords over an empty slice is the partition no-op (no dirty models).
	updated, err := c.updateRecords(context.Background(), "tblStub", nil, false)
	if err != nil {
		t.Fatalf("empty updateRecords should not error: %v", err)
	}
	if len(updated) != 0 {
		t.Fatalf("empty updateRecords returned %d, want 0", len(updated))
	}
	if len(rt.requests) != 0 {
		t.Fatalf("empty updateRecords must make no requests, made %d", len(rt.requests))
	}
}
