package airtable

import (
	"encoding/json"
	"testing"
)

// Airtable's create endpoint is a strict whitelist for attachments: only {url} /
// {url, filename}. Verified against the live API -- an id, alone or echoed alongside url,
// fails with INVALID_ATTACHMENT_OBJECT.
func TestProjectAttachmentsForCreateStripsReadonlyMetadata(t *testing.T) {
	fields := map[string]json.RawMessage{
		"fldAtt": json.RawMessage(`[{"id":"attServerSide1","url":"https://example.com/a.png","filename":"a.png","size":1234,"type":"image/png","thumbnails":{"small":{"url":"x"}}}]`),
	}
	got := projectAttachmentsForCreate(fields)

	var items []map[string]any
	if err := json.Unmarshal(got["fldAtt"], &items); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("want 1 attachment, got %d", len(items))
	}
	if _, ok := items[0]["id"]; ok {
		t.Error("id must be dropped: create rejects it with INVALID_ATTACHMENT_OBJECT")
	}
	for _, k := range []string{"size", "type", "thumbnails"} {
		if _, ok := items[0][k]; ok {
			t.Errorf("read-only key %q must be dropped", k)
		}
	}
	if items[0]["url"] != "https://example.com/a.png" || items[0]["filename"] != "a.png" {
		t.Errorf("url/filename not preserved: %v", items[0])
	}
}

func TestProjectAttachmentsForCreateLeavesOtherCellTypesAlone(t *testing.T) {
	// Linked records, collaborators and plain arrays must not be mistaken for attachments.
	fields := map[string]json.RawMessage{
		"fldLink":  json.RawMessage(`["rec1","rec2"]`),
		"fldUser":  json.RawMessage(`{"id":"usrX","email":"e@x.com"}`),
		"fldUsers": json.RawMessage(`[{"id":"usrX","email":"e@x.com"}]`),
		"fldEmpty": json.RawMessage(`[]`),
		"fldText":  json.RawMessage(`"https://example.com"`),
	}
	got := projectAttachmentsForCreate(fields)
	for k, want := range fields {
		if string(got[k]) != string(want) {
			t.Errorf("%s changed: %s -> %s", k, want, got[k])
		}
	}
}

func TestProjectAttachmentsForCreateDoesNotMutateInput(t *testing.T) {
	original := `[{"id":"attX","url":"u","size":1}]`
	fields := map[string]json.RawMessage{"fldAtt": json.RawMessage(original)}
	projectAttachmentsForCreate(fields)
	if string(fields["fldAtt"]) != original {
		t.Errorf("caller's map was mutated: %s", fields["fldAtt"])
	}
}
