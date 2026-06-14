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
