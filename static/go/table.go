package airtable

// Table[T,PT] is the typed ORM table surface. T is the model struct and PT its
// pointer (which implements Model) — the pointer-constraint idiom lets the table
// allocate new(T), decode into it, and call Model methods. Generated code
// instantiates one Table per table on the Airtable struct.

import (
	"context"
	"encoding/json"
)

type Table[T any, PT interface {
	*T
	Model
}] struct {
	client   *Client
	tableID  string
	nameToID map[string]string
}

// NewTable constructs a typed table. Used by generated code.
func NewTable[T any, PT interface {
	*T
	Model
}](client *Client, tableID string, nameToID map[string]string) *Table[T, PT] {
	return &Table[T, PT]{client: client, tableID: tableID, nameToID: nameToID}
}

// Dict returns a raw dict-table view of the same table.
func (t *Table[T, PT]) Dict() *DictTable {
	return NewDictTable(t.client, t.tableID, t.nameToID)
}

func (t *Table[T, PT]) decode(rec *rawRecord) (PT, error) {
	var v T
	pt := PT(&v)
	if err := hydrate(pt, rec, t.client); err != nil {
		return nil, err
	}
	return pt, nil
}

// Get fetches a single record by ID.
func (t *Table[T, PT]) Get(ctx context.Context, id string) (PT, error) {
	rec, err := t.client.getRecord(ctx, t.tableID, id)
	if err != nil {
		return nil, err
	}
	return t.decode(rec)
}

// List fetches all records matching q (nil for all).
func (t *Table[T, PT]) List(ctx context.Context, q *Query) ([]PT, error) {
	recs, err := t.client.listRecords(ctx, t.tableID, q)
	if err != nil {
		return nil, err
	}
	return t.decodeAll(recs)
}

// Create inserts a single model, hydrating it from the response.
func (t *Table[T, PT]) Create(ctx context.Context, m PT) (PT, error) {
	recs, err := t.client.createRecords(ctx, t.tableID, []map[string]json.RawMessage{toCreateFields(m)}, false)
	if err != nil {
		return nil, err
	}
	if len(recs) == 0 {
		return nil, ErrNotFound
	}
	if err := hydrate(m, &recs[0], t.client); err != nil {
		return nil, err
	}
	return m, nil
}

// CreateMany inserts multiple models (batched), hydrating each from the response.
func (t *Table[T, PT]) CreateMany(ctx context.Context, models []PT) ([]PT, error) {
	payload := make([]map[string]json.RawMessage, 0, len(models))
	for _, m := range models {
		payload = append(payload, toCreateFields(m))
	}
	recs, err := t.client.createRecords(ctx, t.tableID, payload, false)
	if err != nil {
		return nil, err
	}
	for i := range recs {
		if i < len(models) {
			if err := hydrate(models[i], &recs[i], t.client); err != nil {
				return nil, err
			}
		}
	}
	return t.decodeAll(recs)
}

// Update PATCHes a model's dirty fields, hydrating it from the response.
func (t *Table[T, PT]) Update(ctx context.Context, m PT) (PT, error) {
	if m.ID() == "" {
		return nil, ErrNotFound
	}
	recs, err := t.client.updateRecords(ctx, t.tableID, []recordPayload{{ID: m.ID(), Fields: dirtyFields(m)}}, false)
	if err != nil {
		return nil, err
	}
	if len(recs) == 0 {
		return nil, ErrNotFound
	}
	if err := hydrate(m, &recs[0], t.client); err != nil {
		return nil, err
	}
	return m, nil
}

// Delete removes a record by ID.
func (t *Table[T, PT]) Delete(ctx context.Context, id string) error {
	return t.client.deleteRecords(ctx, t.tableID, []string{id})
}

// Upsert inserts or updates m, matching existing records on matchFields (field IDs).
func (t *Table[T, PT]) Upsert(ctx context.Context, m PT, matchFields []string) (PT, error) {
	recs, err := t.client.upsertRecords(ctx, t.tableID, []recordPayload{{Fields: toCreateFields(m)}}, matchFields)
	if err != nil {
		return nil, err
	}
	if len(recs) == 0 {
		return nil, ErrNotFound
	}
	if err := hydrate(m, &recs[0], t.client); err != nil {
		return nil, err
	}
	return m, nil
}

func (t *Table[T, PT]) decodeAll(recs []rawRecord) ([]PT, error) {
	out := make([]PT, 0, len(recs))
	for i := range recs {
		pt, err := t.decode(&recs[i])
		if err != nil {
			return nil, err
		}
		out = append(out, pt)
	}
	return out, nil
}
