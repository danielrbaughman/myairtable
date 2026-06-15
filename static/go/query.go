package airtable

// Query builds the list-record query parameters: filterByFormula, sorts, field
// selection, pagination, view, and returnFieldsByFieldId.

import (
	"net/url"
	"strconv"
)

type Query struct {
	Filter                string
	Sorts                 []Sort
	Fields                []string
	MaxRecords            int
	PageSize              int
	View                  string
	ReturnFieldsByFieldID bool
}

// WithFilter sets filterByFormula.
func (q *Query) WithFilter(formula string) *Query { q.Filter = formula; return q }

// WithSort appends a sort spec.
func (q *Query) WithSort(field string, dir SortDirection) *Query {
	q.Sorts = append(q.Sorts, Sort{Field: field, Direction: dir})
	return q
}

// WithFields restricts the returned fields.
func (q *Query) WithFields(fields ...string) *Query { q.Fields = fields; return q }

// WithMaxRecords caps the total records returned.
func (q *Query) WithMaxRecords(n int) *Query { q.MaxRecords = n; return q }

// WithPageSize sets the per-page size.
func (q *Query) WithPageSize(n int) *Query { q.PageSize = n; return q }

// WithView restricts the query to a view (accepts a generated View constant).
func (q *Query) WithView(v View) *Query { q.View = v.ViewID(); return q }

// WithReturnFieldsByFieldID requests field IDs as JSON keys (required so the
// generated models can decode by field ID).
func (q *Query) WithReturnFieldsByFieldID(b bool) *Query { q.ReturnFieldsByFieldID = b; return q }

// toValues renders the query as URL parameters. offset is the pagination cursor
// (empty for the first page).
func (q *Query) toValues(offset string) url.Values {
	v := url.Values{}
	if q == nil {
		if offset != "" {
			v.Set("offset", offset)
		}
		return v
	}
	if q.Filter != "" {
		v.Set("filterByFormula", q.Filter)
	}
	for i, s := range q.Sorts {
		v.Set("sort["+strconv.Itoa(i)+"][field]", s.Field)
		dir := s.Direction
		if dir == "" {
			dir = SortAsc
		}
		v.Set("sort["+strconv.Itoa(i)+"][direction]", string(dir))
	}
	for _, f := range q.Fields {
		v.Add("fields[]", f)
	}
	if q.MaxRecords > 0 {
		v.Set("maxRecords", strconv.Itoa(q.MaxRecords))
	}
	if q.PageSize > 0 {
		v.Set("pageSize", strconv.Itoa(q.PageSize))
	}
	if q.View != "" {
		v.Set("view", q.View)
	}
	if q.ReturnFieldsByFieldID {
		v.Set("returnFieldsByFieldId", "true")
	}
	if offset != "" {
		v.Set("offset", offset)
	}
	return v
}

// cacheKey returns a stable string identifying this query for cache lookups.
func (q *Query) cacheKey() string {
	if q == nil {
		return ""
	}
	return q.toValues("").Encode()
}
