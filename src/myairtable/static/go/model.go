package airtable

// Model is implemented by every generated {Table}Model. The typed Table[T,PT]
// and the per-model fluent Save/Fetch/Delete methods drive CRUD through this
// interface. Generated models supply writableFields() (their writable field
// set); the create-payload / dirty-diff / snapshot logic lives here so the
// generated code stays thin.

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
)

// Model is the contract every generated model satisfies (pointer receiver).
type Model interface {
	// TableID returns the Airtable table ID this model belongs to.
	TableID() string
	// ID returns the record ID ("" when unsaved).
	ID() string
	// writableFields returns every writable field keyed by field ID (nil values
	// marshal to JSON null).
	writableFields() map[string]json.RawMessage
	setID(string)
	setCreatedTime(*AirtableTime)
	setClient(*Client)
	getClient() *Client
	setSnapshot(map[string]json.RawMessage)
	snapshotFields() map[string]json.RawMessage
}

// mustMarshal marshals a field value to raw JSON, falling back to null on error
// (only basic/JSON-able field types are ever passed here).
func mustMarshal(v any) json.RawMessage {
	b, err := json.Marshal(v)
	if err != nil {
		return json.RawMessage("null")
	}
	return b
}

func isJSONNull(b json.RawMessage) bool { return string(bytes.TrimSpace(b)) == "null" }

// createPayload is the writable fields with null (absent) values dropped.
func createPayload(writable map[string]json.RawMessage) map[string]json.RawMessage {
	out := make(map[string]json.RawMessage, len(writable))
	for k, v := range writable {
		if !isJSONNull(v) {
			out[k] = v
		}
	}
	return out
}

// diffFields returns the entries of current that differ from snapshot (added,
// changed, or cleared — a clear sends JSON null so the field is unset).
func diffFields(snapshot, current map[string]json.RawMessage) map[string]json.RawMessage {
	out := map[string]json.RawMessage{}
	for k, v := range current {
		old, ok := snapshot[k]
		if !ok || !bytes.Equal(old, v) {
			out[k] = v
		}
	}
	return out
}

// projectAttachmentsForCreate reduces attachment cells to the only shape Airtable accepts
// when inserting.
//
// Airtable returns attachments carrying read-only metadata (id, size, type, thumbnails,
// width, height). On *create* it accepts only {"url": ...} (optionally with "filename") --
// sending an id, alone or echoed alongside url, fails with INVALID_ATTACHMENT_OBJECT.
// Airtable re-ingests the file and mints a fresh attachment id, which is what makes a
// duplicated record's attachment independent of its source rather than an alias.
//
// Create-only: on *update* an id is legal and means "retain this attachment".
//
// Cells are recognised by shape rather than by field ID, so this needs no generated
// metadata: no other Airtable cell type is an array of objects carrying a url alongside an
// att-prefixed id. Returns a new map; the caller's fields are never mutated.
func projectAttachmentsForCreate(fields map[string]json.RawMessage) map[string]json.RawMessage {
	out := make(map[string]json.RawMessage, len(fields))
	for k, v := range fields {
		out[k] = v
		var items []map[string]json.RawMessage
		if err := json.Unmarshal(v, &items); err != nil || len(items) == 0 {
			continue
		}
		projected := make([]map[string]json.RawMessage, 0, len(items))
		isAttachmentCell := true
		for _, item := range items {
			url, hasURL := item["url"]
			rawID, hasID := item["id"]
			if !hasURL || !hasID {
				isAttachmentCell = false
				break
			}
			var id string
			if err := json.Unmarshal(rawID, &id); err != nil || !strings.HasPrefix(id, "att") {
				isAttachmentCell = false
				break
			}
			entry := map[string]json.RawMessage{"url": url}
			if filename, ok := item["filename"]; ok && string(filename) != "null" {
				entry["filename"] = filename
			}
			projected = append(projected, entry)
		}
		if !isAttachmentCell {
			continue
		}
		if encoded, err := json.Marshal(projected); err == nil {
			out[k] = encoded
		}
	}
	return out
}

// toCreateFields / dirtyFields are computed from the model's current writable set.
func toCreateFields(m Model) map[string]json.RawMessage { return createPayload(m.writableFields()) }
func dirtyFields(m Model) map[string]json.RawMessage {
	return diffFields(m.snapshotFields(), m.writableFields())
}

// hydrate decodes a record envelope into a model and resets its snapshot.
func hydrate(m Model, rec *rawRecord, client *Client) error {
	if len(rec.Fields) > 0 {
		if err := json.Unmarshal(rec.Fields, m); err != nil {
			return &DecodingError{Err: err}
		}
	}
	m.setID(rec.ID)
	m.setCreatedTime(rec.CreatedTime)
	m.setClient(client)
	m.setSnapshot(m.writableFields())
	return nil
}

// ---- generic per-model fluent operations (backing generated Save/Fetch/Delete) ----

func modelClient(m Model) (*Client, error) {
	c := m.getClient()
	if c == nil {
		return nil, ErrMissingCredentials
	}
	return c, nil
}

func modelSave[T any, PT interface {
	*T
	Model
}](ctx context.Context, m PT) error {
	client, err := modelClient(m)
	if err != nil {
		return err
	}
	if m.ID() == "" {
		recs, err := client.createRecords(ctx, m.TableID(), []map[string]json.RawMessage{toCreateFields(m)}, false)
		if err != nil {
			return err
		}
		if len(recs) == 0 {
			return ErrNotFound
		}
		return hydrate(m, &recs[0], client)
	}
	recs, err := client.updateRecords(ctx, m.TableID(), []recordPayload{{ID: m.ID(), Fields: dirtyFields(m)}}, false)
	if err != nil {
		return err
	}
	if len(recs) == 0 {
		return ErrNotFound
	}
	return hydrate(m, &recs[0], client)
}

func modelFetch[T any, PT interface {
	*T
	Model
}](ctx context.Context, m PT) error {
	client, err := modelClient(m)
	if err != nil {
		return err
	}
	if m.ID() == "" {
		return ErrNotFound
	}
	rec, err := client.getRecord(ctx, m.TableID(), m.ID())
	if err != nil {
		return err
	}
	return hydrate(m, rec, client)
}

func modelDelete[T any, PT interface {
	*T
	Model
}](ctx context.Context, m PT) error {
	client, err := modelClient(m)
	if err != nil {
		return err
	}
	if m.ID() == "" {
		return ErrNotFound
	}
	if err := client.deleteRecords(ctx, m.TableID(), []string{m.ID()}); err != nil {
		return err
	}
	m.setID("")
	return nil
}

// copyModel returns a detached, unsaved deep copy of a model.
//
// Named Copy for symmetry with the other nine targets, NOT for Go's builtin copy():
// the idiomatic Go name for an independent duplicate is Clone (maps.Clone,
// slices.Clone, http.Header.Clone), and Clone is what this does. Nothing is copied
// into a destination the caller supplies, and nothing is truncated to a length.
//
// The copy carries every field value -- computed ones included, so it reads like its
// source -- but none of the record's identity, so Save(ctx) INSERTS it as a new record
// instead of patching the original. Mutate it and Save it, or hand it to CreateOne.
//
// Performs no I/O. That is the whole difference from DuplicateOne, which POSTs; a copy
// is therefore only as fresh as the model in hand, which matters most for attachments
// (their signed URLs expire after roughly two hours).
//
// Detaching is what makes this safe, and here it is structural: the clone is a FRESH
// new(T), so id, createdTime and snapshot start zero and there is no way to forget one.
// The tempting `*clone = *src` (legal inside this package) is exactly what is avoided --
// Go struct assignment is shallow, so it would alias every slice, map and pointer with
// the source, and a mutation of the copy's option or attachment slice would be felt by
// the original. id is the load-bearing field: modelSave branches on ID() == "", so a
// copy that kept it would PATCH the source. The client handle IS kept, deliberately --
// that is what lets copy.Save(ctx) work without re-plumbing a table.
//
// Values move through JSON rather than through reflection. Every field's Go type already
// declares a total, round-trippable JSON encoding (that is how records are hydrated in the
// first place), and encoding/json allocates fresh containers on the way in, which is the
// deep copy -- for free, and without the unsafe games reflection would need to reach the
// unexported fields inside wrappers like MaybeSpecialOrError. The one lossy edge is
// AirtableTime, whose MarshalJSON truncates to whole seconds; that truncation is already
// what any write of that value would have sent, so the copy matches the wire, not the
// clock.
//
// Attachments are projected to {url, filename} here, at copy time, because Airtable
// rejects server-returned attachment objects on create, and copying by URL is what makes
// the created record own an independent attachment rather than aliasing the source's.
// Only WRITABLE cells are projected: a computed lookup can hold the very same shape, is
// never written back, and stripping its metadata would lose fidelity for nothing.
//
// A JSON error is unreachable for generated models; should one occur the clone is
// returned as far as it got, detached and never aliased -- degraded, never dangerous.
func copyModel[T any, PT interface {
	*T
	Model
}](src PT) PT {
	clone := PT(new(T))
	clone.setClient(src.getClient())

	// Marshal through the model's own json tags: the result is keyed by field ID,
	// exactly like a record envelope's "fields", and carries computed cells too
	// (unexported id/createdTime/client/snapshot have no tags and cannot leak in).
	raw, err := json.Marshal(src)
	if err != nil {
		return clone
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return clone
	}

	// writableFields() is the generated writable-only whitelist, so its key set is the
	// exact set of cells that may be projected.
	writable := make(map[string]json.RawMessage, len(fields))
	for id := range src.writableFields() {
		if value, ok := fields[id]; ok {
			writable[id] = value
		}
	}
	for id, projected := range projectAttachmentsForCreate(writable) {
		fields[id] = projected
	}

	encoded, err := json.Marshal(fields)
	if err != nil {
		return clone
	}
	// Decode failures are per-field and already reported by hydrate's path; ignoring the
	// error here mirrors that, and cannot leave shared state behind.
	_ = json.Unmarshal(encoded, clone)
	return clone
}
