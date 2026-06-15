package airtable

// DictTable is the raw, untyped table surface: records are returned as Fields
// (field-ID -> raw JSON with dual ID/name access). It mirrors the typed Table
// API and is what the generated per-table dict accessor builds on.

import (
	"context"
	"encoding/json"
)

// DictRecord is a raw record: its envelope metadata plus untyped Fields.
type DictRecord struct {
	ID          string
	CreatedTime *AirtableTime
	Fields      *Fields
}

type DictTable struct {
	client   *Client
	tableID  string
	nameToID map[string]string
}

// NewDictTable constructs a raw table view. nameToID (from the generated
// {Table}Fields metadata) enables name-based field access; nil is allowed.
func NewDictTable(client *Client, tableID string, nameToID map[string]string) *DictTable {
	return &DictTable{client: client, tableID: tableID, nameToID: nameToID}
}

func (t *DictTable) wrap(rec *rawRecord) (*DictRecord, error) {
	values := map[string]json.RawMessage{}
	if len(rec.Fields) > 0 {
		if err := json.Unmarshal(rec.Fields, &values); err != nil {
			return nil, &DecodingError{Err: err}
		}
	}
	return &DictRecord{ID: rec.ID, CreatedTime: rec.CreatedTime, Fields: NewFields(values, t.nameToID)}, nil
}

// GetOne fetches a single record by ID.
func (t *DictTable) GetOne(ctx context.Context, id string) (*DictRecord, error) {
	rec, err := t.client.getRecord(ctx, t.tableID, id)
	if err != nil {
		return nil, err
	}
	return t.wrap(rec)
}

// GetMany fetches all records matching q (nil for all records).
func (t *DictTable) GetMany(ctx context.Context, q *Query) ([]*DictRecord, error) {
	recs, err := t.client.listRecords(ctx, t.tableID, q)
	if err != nil {
		return nil, err
	}
	out := make([]*DictRecord, 0, len(recs))
	for i := range recs {
		dr, err := t.wrap(&recs[i])
		if err != nil {
			return nil, err
		}
		out = append(out, dr)
	}
	return out, nil
}

// CreateOne inserts a single record from the given fields.
func (t *DictTable) CreateOne(ctx context.Context, fields *Fields) (*DictRecord, error) {
	created, err := t.CreateMany(ctx, []*Fields{fields})
	if err != nil {
		return nil, err
	}
	if len(created) == 0 {
		return nil, ErrNotFound
	}
	return created[0], nil
}

// CreateMany inserts multiple records (batched in chunks of 10).
func (t *DictTable) CreateMany(ctx context.Context, fields []*Fields) ([]*DictRecord, error) {
	payload := make([]map[string]json.RawMessage, 0, len(fields))
	for _, f := range fields {
		payload = append(payload, f.Raw())
	}
	recs, err := t.client.createRecords(ctx, t.tableID, payload, false)
	if err != nil {
		return nil, err
	}
	return t.wrapAll(recs)
}

// UpdateOne PATCHes a single record's fields.
func (t *DictTable) UpdateOne(ctx context.Context, id string, fields *Fields) (*DictRecord, error) {
	recs, err := t.client.updateRecords(ctx, t.tableID, []recordPayload{{ID: id, Fields: fields.Raw()}}, false)
	if err != nil {
		return nil, err
	}
	wrapped, err := t.wrapAll(recs)
	if err != nil {
		return nil, err
	}
	if len(wrapped) == 0 {
		return nil, ErrNotFound
	}
	return wrapped[0], nil
}

// DeleteOne removes a single record by ID.
func (t *DictTable) DeleteOne(ctx context.Context, id string) error {
	return t.client.deleteRecords(ctx, t.tableID, []string{id})
}

// DeleteMany removes multiple records by ID (batched in chunks of 10).
func (t *DictTable) DeleteMany(ctx context.Context, ids []string) error {
	return t.client.deleteRecords(ctx, t.tableID, ids)
}

func (t *DictTable) wrapAll(recs []rawRecord) ([]*DictRecord, error) {
	out := make([]*DictRecord, 0, len(recs))
	for i := range recs {
		dr, err := t.wrap(&recs[i])
		if err != nil {
			return nil, err
		}
		out = append(out, dr)
	}
	return out, nil
}
