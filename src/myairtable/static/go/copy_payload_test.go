package airtable

// Hermetic tests for Copy() — the purely local half of duplicate(). copy makes no
// network calls, so unlike DuplicateOne it is 100% testable offline; the one place a
// transport appears here is to prove that a copy SAVES AS AN INSERT (POST), which is
// the whole point of clearing the id.
//
// The fixture below mirrors exactly what generators/go.py emits for a model: exported
// fields tagged by field ID, four unexported detach fields, a writableFields() that is
// the writable-only whitelist, and a one-line Copy() forwarder onto copyModel.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

type copyFixtureModel struct {
	Name  *string              `json:"fldName,omitempty"`
	Tags  []string             `json:"fldTags,omitempty"`
	Files []AirtableAttachment `json:"fldFiles,omitempty"`
	Links []string             `json:"fldLinks,omitempty"`

	// Computed: decode-only, deliberately absent from writableFields().
	Rollup        *string              `json:"fldRollup,omitempty"`
	LookedUpFiles []AirtableAttachment `json:"fldLookupFiles,omitempty"`

	id          string
	createdTime *AirtableTime
	client      *Client
	snapshot    map[string]json.RawMessage
}

func (m *copyFixtureModel) TableID() string                { return "tblCopy" }
func (m *copyFixtureModel) ID() string                     { return m.id }
func (m *copyFixtureModel) CreatedTime() *AirtableTime     { return m.createdTime }
func (m *copyFixtureModel) setID(id string)                { m.id = id }
func (m *copyFixtureModel) setCreatedTime(t *AirtableTime) { m.createdTime = t }
func (m *copyFixtureModel) setClient(c *Client)            { m.client = c }
func (m *copyFixtureModel) getClient() *Client             { return m.client }
func (m *copyFixtureModel) setSnapshot(s map[string]json.RawMessage) {
	m.snapshot = s
}
func (m *copyFixtureModel) snapshotFields() map[string]json.RawMessage { return m.snapshot }

// writableFields is the writable-only whitelist — the computed cells never appear, which
// is what makes carrying their VALUES on a copy safe on the wire.
func (m *copyFixtureModel) writableFields() map[string]json.RawMessage {
	return map[string]json.RawMessage{
		"fldName":  mustMarshal(m.Name),
		"fldTags":  mustMarshal(m.Tags),
		"fldFiles": mustMarshal(m.Files),
		"fldLinks": mustMarshal(m.Links),
	}
}

func (m *copyFixtureModel) Copy() *copyFixtureModel { return copyModel[copyFixtureModel](m) }

// newCopyFixtureSource builds a fully hydrated, server-backed model: an id, a
// createdTime, a snapshot and every field kind populated.
func newCopyFixtureSource(t *testing.T, client *Client) *copyFixtureModel {
	t.Helper()
	size := int64(1234)
	m := &copyFixtureModel{
		Name: String("original"),
		Tags: []string{"alpha", "beta"},
		Files: []AirtableAttachment{{
			ID:         "attServerSide1",
			URL:        "https://example.com/a.png",
			Filename:   "a.png",
			Size:       &size,
			Type:       "image/png",
			Thumbnails: &AirtableThumbnails{Small: &Thumbnail{URL: "https://example.com/t.png"}},
		}},
		Links:  []string{"recLinkedA", "recLinkedB"},
		Rollup: String("computed-value"),
		LookedUpFiles: []AirtableAttachment{{
			ID:       "attLookedUp1",
			URL:      "https://example.com/lookup.png",
			Filename: "lookup.png",
			Size:     &size,
			Type:     "image/png",
		}},
		id:     "recSource",
		client: client,
	}
	created := &AirtableTime{}
	if err := created.UnmarshalJSON([]byte(`"2024-01-02T03:04:05.000Z"`)); err != nil {
		t.Fatalf("seed createdTime: %v", err)
	}
	m.createdTime = created
	m.snapshot = m.writableFields()
	return m
}

// ---- the detach ------------------------------------------------------------

func TestCopyDetachesRecordIdentity(t *testing.T) {
	client := NewClient("key", "appXXX", 0)
	src := newCopyFixtureSource(t, client)

	got := src.Copy()

	if got == src {
		t.Fatal("Copy must return a new instance, not the receiver")
	}
	if got.ID() != "" {
		// modelSave branches on ID() == ""; a carried id would PATCH the source.
		t.Errorf("id must be cleared, got %q", got.ID())
	}
	if got.CreatedTime() != nil {
		t.Errorf("createdTime must be cleared, got %v", got.CreatedTime())
	}
	if got.snapshotFields() != nil {
		t.Errorf("snapshot must be nil so the copy is not diffed against the source's state, got %v", got.snapshotFields())
	}
	if got.getClient() != client {
		t.Error("client must be RETAINED so copy.Save(ctx) can insert without re-plumbing a table")
	}
}

// The load-bearing consequence of the detach: saving a copy INSERTS.
func TestCopySavesAsInsertAndLeavesTheSourceRow(t *testing.T) {
	rt := &copyCapturingTransport{}
	client := clientWithTransport(rt)
	src := newCopyFixtureSource(t, client)

	got := src.Copy()
	if err := modelSave[copyFixtureModel](context.Background(), got); err != nil {
		t.Fatalf("Save: %v", err)
	}

	if len(rt.methods) != 1 {
		t.Fatalf("expected exactly 1 request, got %v", rt.methods)
	}
	if rt.methods[0] != http.MethodPost {
		t.Errorf("a copy must INSERT: want POST, got %s", rt.methods[0])
	}
	if strings.Contains(rt.bodies[0], "recSource") {
		t.Errorf("the source's record id leaked into the create body: %s", rt.bodies[0])
	}
	if src.ID() != "recSource" {
		t.Errorf("the source record must be untouched, its id is now %q", src.ID())
	}
	if got.ID() == "" {
		t.Error("the copy should have been hydrated with the server's new id")
	}
}

func TestCopyPerformsNoIO(t *testing.T) {
	rt := &copyCapturingTransport{}
	src := newCopyFixtureSource(t, clientWithTransport(rt))

	_ = src.Copy()

	if len(rt.methods) != 0 {
		t.Errorf("Copy must perform ZERO I/O, saw %v", rt.methods)
	}
}

// ---- computed values: readable, but never on the wire ----------------------

func TestCopyCarriesComputedValuesButKeepsThemOutOfTheCreatePayload(t *testing.T) {
	src := newCopyFixtureSource(t, nil)

	got := src.Copy()

	if got.Rollup == nil || *got.Rollup != "computed-value" {
		t.Fatalf("computed value must be carried so the copy reads like its source, got %v", got.Rollup)
	}
	payload := toCreateFields(got)
	for _, id := range []string{"fldRollup", "fldLookupFiles"} {
		if _, ok := payload[id]; ok {
			t.Errorf("computed field %s must not reach the create body (Airtable 422s on it)", id)
		}
	}
	for _, id := range []string{"fldName", "fldTags", "fldFiles", "fldLinks"} {
		if _, ok := payload[id]; !ok {
			t.Errorf("writable field %s is missing from the create body", id)
		}
	}
}

// ---- attachments ------------------------------------------------------------

func TestCopyProjectsWritableAttachmentsButNotComputedOnes(t *testing.T) {
	src := newCopyFixtureSource(t, nil)

	got := src.Copy()

	if len(got.Files) != 1 {
		t.Fatalf("want 1 writable attachment, got %d", len(got.Files))
	}
	writable := got.Files[0]
	if writable.ID != "" {
		t.Errorf("attachment id must be stripped: create fails with INVALID_ATTACHMENT_OBJECT, got %q", writable.ID)
	}
	if writable.Size != nil || writable.Type != "" || writable.Thumbnails != nil {
		t.Errorf("read-only attachment metadata must be stripped, got %+v", writable)
	}
	if writable.URL != "https://example.com/a.png" || writable.Filename != "a.png" {
		t.Errorf("url/filename must survive — that is how Airtable re-ingests the file, got %+v", writable)
	}

	// A computed lookup can hold the very same shape. It is never written back, so
	// stripping its metadata would lose fidelity for nothing.
	if len(got.LookedUpFiles) != 1 {
		t.Fatalf("want 1 computed attachment, got %d", len(got.LookedUpFiles))
	}
	lookedUp := got.LookedUpFiles[0]
	if lookedUp.ID != "attLookedUp1" || lookedUp.Size == nil || lookedUp.Type != "image/png" {
		t.Errorf("computed attachment cell must keep its full metadata, got %+v", lookedUp)
	}
}

// ---- no shared mutable state ------------------------------------------------

func TestCopyDeepCopiesEveryContainer(t *testing.T) {
	src := newCopyFixtureSource(t, nil)

	got := src.Copy()

	if got.Name == src.Name {
		t.Error("scalar pointer is aliased with the source")
	}
	if len(got.Tags) != 0 && len(src.Tags) != 0 && &got.Tags[0] == &src.Tags[0] {
		t.Error("option slice is aliased with the source")
	}
	if &got.Files[0] == &src.Files[0] {
		t.Error("attachment slice is aliased with the source")
	}
	if &got.Links[0] == &src.Links[0] {
		t.Error("linked-record slice is aliased with the source")
	}
	if got.LookedUpFiles[0].Size == src.LookedUpFiles[0].Size {
		t.Error("a pointer nested inside a computed cell is aliased with the source")
	}

	// Mutating the copy must be invisible to the source, and vice versa.
	*got.Name = "mutated"
	got.Tags[0] = "mutated"
	got.Links = append(got.Links, "recLinkedC")
	got.Files[0].Filename = "mutated.png"
	*got.LookedUpFiles[0].Size = 99

	if *src.Name != "original" || src.Tags[0] != "alpha" || len(src.Links) != 2 {
		t.Errorf("mutating the copy changed the source: %v %v %v", *src.Name, src.Tags, src.Links)
	}
	if src.Files[0].Filename != "a.png" {
		t.Errorf("mutating the copy's attachment changed the source: %q", src.Files[0].Filename)
	}
	if *src.LookedUpFiles[0].Size != 1234 {
		t.Errorf("mutating the copy's computed cell changed the source: %d", *src.LookedUpFiles[0].Size)
	}

	src.Tags[1] = "reverse-mutated"
	if got.Tags[1] != "beta" {
		t.Errorf("mutating the source changed the copy: %q", got.Tags[1])
	}
}

// ---- the source is inert throughout ----------------------------------------

func TestCopyLeavesTheSourceCompletelyUntouched(t *testing.T) {
	client := NewClient("key", "appXXX", 0)
	src := newCopyFixtureSource(t, client)
	before, err := json.Marshal(src)
	if err != nil {
		t.Fatalf("marshal source: %v", err)
	}
	beforeCreated := src.CreatedTime()
	beforeSnapshot := src.snapshotFields()

	_ = src.Copy()

	after, err := json.Marshal(src)
	if err != nil {
		t.Fatalf("marshal source: %v", err)
	}
	if string(before) != string(after) {
		t.Errorf("source fields changed:\n before: %s\n  after: %s", before, after)
	}
	if src.ID() != "recSource" || src.CreatedTime() != beforeCreated || src.getClient() != client {
		t.Error("source record metadata changed")
	}
	// Same map, not merely an equal one: nothing re-snapshotted the source.
	if len(beforeSnapshot) != len(src.snapshotFields()) {
		t.Error("source snapshot was replaced")
	}
	for k, v := range beforeSnapshot {
		if string(src.snapshotFields()[k]) != string(v) {
			t.Errorf("source snapshot entry %s changed", k)
		}
	}
}

// A copy of an unsaved, half-populated model is still a valid detached model — nil
// containers must stay nil rather than materialising as empty ones.
func TestCopyOfAnUnsavedModelKeepsAbsentFieldsAbsent(t *testing.T) {
	src := &copyFixtureModel{Name: String("draft")}

	got := src.Copy()

	if got.Name == nil || *got.Name != "draft" {
		t.Fatalf("value not carried: %v", got.Name)
	}
	if got.Tags != nil || got.Files != nil || got.Links != nil || got.Rollup != nil {
		t.Errorf("absent fields must stay absent, got %+v", got)
	}
	if got.ID() != "" || got.getClient() != nil {
		t.Error("a copy of an unsaved model must stay unsaved and clientless")
	}
}

// ---- helpers ----------------------------------------------------------------

// copyCapturingTransport records the method and raw body of every request, so a test
// can assert both that a copy POSTs and that nothing at all was sent.
type copyCapturingTransport struct {
	methods []string
	bodies  []string
}

func (rt *copyCapturingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	rt.methods = append(rt.methods, req.Method)
	body := ""
	if req.Body != nil {
		raw, _ := io.ReadAll(req.Body)
		body = string(raw)
	}
	rt.bodies = append(rt.bodies, body)
	return cannedResponse(`{"records":[{"id":"recCopyCreated","fields":{}}]}`), nil
}
