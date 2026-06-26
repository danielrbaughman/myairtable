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

// Attach binds this table's client to a model so its fluent Save/Fetch/Delete
// methods work (e.g. for inserting a freshly-constructed model). Returns m.
func (t *Table[T, PT]) Attach(m PT) PT {
	m.setClient(t.client)
	return m
}

func (t *Table[T, PT]) decode(rec *rawRecord) (PT, error) {
	var v T
	pt := PT(&v)
	if err := hydrate(pt, rec, t.client); err != nil {
		return nil, err
	}
	return pt, nil
}

// GetOne fetches a single record by ID.
func (t *Table[T, PT]) GetOne(ctx context.Context, id string) (PT, error) {
	rec, err := t.client.getRecord(ctx, t.tableID, id)
	if err != nil {
		return nil, err
	}
	return t.decode(rec)
}

// GetMany fetches all records matching q (nil for all).
func (t *Table[T, PT]) GetMany(ctx context.Context, q *Query) ([]PT, error) {
	recs, err := t.client.listRecords(ctx, t.tableID, q)
	if err != nil {
		return nil, err
	}
	return t.decodeAll(recs)
}

// CreateOne inserts a single model, hydrating it from the response.
func (t *Table[T, PT]) CreateOne(ctx context.Context, m PT, opts ...WriteOption) (PT, error) {
	o := resolveWriteOptions(opts)
	recs, err := t.client.createRecords(ctx, t.tableID, []map[string]json.RawMessage{toCreateFields(m)}, o.typecast)
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
func (t *Table[T, PT]) CreateMany(ctx context.Context, models []PT, opts ...WriteOption) ([]PT, error) {
	o := resolveWriteOptions(opts)
	payload := make([]map[string]json.RawMessage, 0, len(models))
	for _, m := range models {
		payload = append(payload, toCreateFields(m))
	}
	recs, err := t.client.createRecords(ctx, t.tableID, payload, o.typecast)
	if err != nil {
		return nil, err
	}
	return t.hydrateInto(models, recs)
}

// UpdateOne PATCHes a model's dirty fields (or all writable fields when it has
// no snapshot), hydrating it from the response. The model carries its own ID.
func (t *Table[T, PT]) UpdateOne(ctx context.Context, m PT, opts ...WriteOption) (PT, error) {
	if m.ID() == "" {
		return nil, ErrNotFound
	}
	o := resolveWriteOptions(opts)
	recs, err := t.client.updateRecords(ctx, t.tableID, []recordPayload{{ID: m.ID(), Fields: dirtyFields(m)}}, o.typecast)
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

// UpdateMany PATCHes multiple models (batched), each by its own ID.
func (t *Table[T, PT]) UpdateMany(ctx context.Context, models []PT, opts ...WriteOption) ([]PT, error) {
	o := resolveWriteOptions(opts)
	payload := make([]recordPayload, 0, len(models))
	for _, m := range models {
		if m.ID() == "" {
			return nil, ErrNotFound
		}
		payload = append(payload, recordPayload{ID: m.ID(), Fields: dirtyFields(m)})
	}
	recs, err := t.client.updateRecords(ctx, t.tableID, payload, o.typecast)
	if err != nil {
		return nil, err
	}
	return t.hydrateInto(models, recs)
}

// hydrateInto refreshes the given models in place from the response records
// (Airtable returns one record per input, in order) and returns the same
// hydrated models — so callers get back the objects they passed in.
func (t *Table[T, PT]) hydrateInto(models []PT, recs []rawRecord) ([]PT, error) {
	for i := range recs {
		if i >= len(models) {
			break
		}
		if err := hydrate(models[i], &recs[i], t.client); err != nil {
			return nil, err
		}
	}
	return models, nil
}

// DeleteOne removes a record by ID.
func (t *Table[T, PT]) DeleteOne(ctx context.Context, id string) error {
	return t.client.deleteRecords(ctx, t.tableID, []string{id})
}

// Upsert inserts or updates m, matching existing records on matchFields (field IDs).
func (t *Table[T, PT]) Upsert(ctx context.Context, m PT, matchFields []string, opts ...WriteOption) (PT, error) {
	o := resolveWriteOptions(opts)
	recs, err := t.client.upsertRecords(ctx, t.tableID, []recordPayload{{Fields: toCreateFields(m)}}, matchFields, o.typecast)
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
