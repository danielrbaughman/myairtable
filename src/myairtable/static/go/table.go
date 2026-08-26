package airtable

// Table[T,PT] is the typed ORM table surface. T is the model struct and PT its
// pointer (which implements Model) — the pointer-constraint idiom lets the table
// allocate new(T), decode into it, and call Model methods. Generated code
// instantiates one Table per table on the Airtable struct.

import (
	"context"
	"encoding/json"
	"fmt"
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

// DuplicateOne copies a record into a brand-new record.
//
// Every writable field is copied verbatim, including the primary field. Computed fields are
// omitted and recalculated by Airtable, so the copy gets its own ID, autonumber and
// timestamps. The returned model is a FRESH instance -- unlike CreateOne, which hydrates the
// model you pass it, so duplicating with CreateOne would overwrite the source's ID with the
// copy's.
//
// Attachments are copied by URL, so Airtable re-ingests each file and the copy owns an
// independent attachment rather than aliasing the source's.
//
// Linked records are copied as-is. Airtable link fields are many-to-many underneath, so the
// copy is added alongside the original on the far side of the link; the source record's own
// links are never modified.
func (t *Table[T, PT]) DuplicateOne(ctx context.Context, m PT, opts ...WriteOption) (PT, error) {
	o := resolveWriteOptions(opts)
	fields := projectAttachmentsForCreate(toCreateFields(m))
	recs, err := t.client.createRecords(ctx, t.tableID, []map[string]json.RawMessage{fields}, o.typecast)
	if err != nil {
		return nil, err
	}
	if len(recs) == 0 {
		return nil, ErrNotFound
	}
	// decode() allocates a fresh model; hydrate() would mutate the caller's.
	return t.decode(&recs[0])
}

// DuplicateMany copies several records into brand-new records (batched at 10 per request).
// The source models are left untouched.
func (t *Table[T, PT]) DuplicateMany(ctx context.Context, models []PT, opts ...WriteOption) ([]PT, error) {
	if len(models) == 0 {
		return nil, nil
	}
	o := resolveWriteOptions(opts)
	payload := make([]map[string]json.RawMessage, 0, len(models))
	for _, m := range models {
		payload = append(payload, projectAttachmentsForCreate(toCreateFields(m)))
	}
	recs, err := t.client.createRecords(ctx, t.tableID, payload, o.typecast)
	if err != nil {
		return nil, err
	}
	return t.decodeAll(recs)
}

// DuplicateOneByID reads the record with id and copies it. Costs one extra GET, and in
// exchange the copy reflects current server state and its attachment URLs are freshly signed
// (Airtable's expire after roughly two hours).
func (t *Table[T, PT]) DuplicateOneByID(ctx context.Context, id string, opts ...WriteOption) (PT, error) {
	source, err := t.GetOne(ctx, id)
	if err != nil {
		return nil, err
	}
	return t.DuplicateOne(ctx, source, opts...)
}

// DuplicateManyByIDs reads the records with ids and copies them, preserving the given order.
func (t *Table[T, PT]) DuplicateManyByIDs(ctx context.Context, ids []string, opts ...WriteOption) ([]PT, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	// One batched read via a RECORD_ID() OR-list, rather than a GET per id.
	q := (&Query{}).WithFilter(NewIDField().InList(ids).String())
	fetched, err := t.GetMany(ctx, q)
	if err != nil {
		return nil, err
	}
	// Airtable returns records in table order, not the order they were asked for.
	byID := make(map[string]PT, len(fetched))
	for _, m := range fetched {
		byID[m.ID()] = m
	}
	ordered := make([]PT, 0, len(ids))
	for _, id := range ids {
		m, ok := byID[id]
		if !ok {
			return nil, fmt.Errorf("duplicate: source record %s was not found: %w", id, ErrNotFound)
		}
		ordered = append(ordered, m)
	}
	return t.DuplicateMany(ctx, ordered, opts...)
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
