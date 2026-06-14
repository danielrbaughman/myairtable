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

// CleanValues unwraps a computed lookup/rollup field — a VecOrValue whose
// elements are each a MaybeSpecialOrError[T] — into the slice of present inner
// values, dropping every element that decoded to a special number or an error.
// It is the null-safe read path for computed list fields (mirrors the Java/Kotlin
// cleanValues DX helper).
func CleanValues[T any](v VecOrValue[MaybeSpecialOrError[T]]) []T {
	elems := v.Values()
	out := make([]T, 0, len(elems))
	for _, e := range elems {
		if val, ok := e.Value(); ok {
			out = append(out, val)
		}
	}
	return out
}
