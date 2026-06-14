package airtable

// VecOrValue[T] models an Airtable lookup/rollup value whose cardinality cannot
// be determined from metadata alone: the API returns either a single T or a
// JSON array of T. Decoding peeks the first token; encoding round-trips the
// captured shape.

import (
	"bytes"
	"encoding/json"
)

type VecOrValue[T any] struct {
	Single     T
	Multiple   []T
	IsMultiple bool
}

// Values returns the contained values as a slice (a single value becomes a
// one-element slice).
func (v VecOrValue[T]) Values() []T {
	if v.IsMultiple {
		return v.Multiple
	}
	return []T{v.Single}
}

func (v *VecOrValue[T]) UnmarshalJSON(b []byte) error {
	trimmed := bytes.TrimSpace(b)
	if len(trimmed) > 0 && trimmed[0] == '[' {
		v.IsMultiple = true
		return json.Unmarshal(b, &v.Multiple)
	}
	v.IsMultiple = false
	return json.Unmarshal(b, &v.Single)
}

func (v VecOrValue[T]) MarshalJSON() ([]byte, error) {
	if v.IsMultiple {
		return json.Marshal(v.Multiple)
	}
	return json.Marshal(v.Single)
}
