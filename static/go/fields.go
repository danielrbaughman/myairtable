package airtable

// Fields is the raw, untyped field container backing the dict-table surface. It
// wraps a map of field-ID -> raw JSON and offers dual ID/name access (ID first,
// falling back to a generated name->ID map supplied by the caller).

import "encoding/json"

type Fields struct {
	values map[string]json.RawMessage
	// nameToID maps human field names to field IDs for name-based access. It is
	// supplied by the generated {Table}Fields metadata; nil is allowed (ID-only).
	nameToID map[string]string
}

// NewFields builds a Fields container. nameToID may be nil for ID-only access.
func NewFields(values map[string]json.RawMessage, nameToID map[string]string) *Fields {
	if values == nil {
		values = map[string]json.RawMessage{}
	}
	return &Fields{values: values, nameToID: nameToID}
}

// resolve returns the field ID for a key that is either a field ID or a field name.
func (f *Fields) resolve(key string) string {
	if _, ok := f.values[key]; ok {
		return key
	}
	if f.nameToID != nil {
		if id, ok := f.nameToID[key]; ok {
			return id
		}
	}
	return key
}

// GetRaw returns the raw JSON for a field by ID or name, and whether it was set.
func (f *Fields) GetRaw(key string) (json.RawMessage, bool) {
	raw, ok := f.values[f.resolve(key)]
	return raw, ok
}

// Get decodes the field identified by key (ID or name) into dst.
func (f *Fields) Get(key string, dst any) error {
	raw, ok := f.values[f.resolve(key)]
	if !ok {
		return ErrNotFound
	}
	if err := json.Unmarshal(raw, dst); err != nil {
		return &DecodingError{Err: err}
	}
	return nil
}

// Set assigns a value to a field (by ID or name).
func (f *Fields) Set(key string, value any) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return &DecodingError{Err: err}
	}
	f.values[f.resolve(key)] = raw
	return nil
}

// Raw returns the underlying field-ID -> raw JSON map.
func (f *Fields) Raw() map[string]json.RawMessage { return f.values }
