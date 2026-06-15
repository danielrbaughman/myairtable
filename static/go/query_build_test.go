package airtable

// White-box tests for Query.toValues / Query.cacheKey. Mirrors the Java
// TestAirtableQueryBuild cases adapted to the Go API.

import (
	"net/url"
	"testing"
)

func TestQueryToValuesFilter(t *testing.T) {
	q := (&Query{}).WithFilter("{Name}='x'")
	v := q.toValues("")
	if got := v.Get("filterByFormula"); got != "{Name}='x'" {
		t.Fatalf("filterByFormula = %q, want %q", got, "{Name}='x'")
	}
}

func TestQueryToValuesEmptyOmitsFilter(t *testing.T) {
	v := (&Query{}).toValues("")
	if _, ok := v["filterByFormula"]; ok {
		t.Fatalf("empty filter should not be set, got %v", v)
	}
}

func TestQueryToValuesSorts(t *testing.T) {
	q := (&Query{}).
		WithSort("Name", SortAsc).
		WithSort("Age", SortDesc)
	v := q.toValues("")
	if got := v.Get("sort[0][field]"); got != "Name" {
		t.Fatalf("sort[0][field] = %q, want Name", got)
	}
	if got := v.Get("sort[0][direction]"); got != "asc" {
		t.Fatalf("sort[0][direction] = %q, want asc", got)
	}
	if got := v.Get("sort[1][field]"); got != "Age" {
		t.Fatalf("sort[1][field] = %q, want Age", got)
	}
	if got := v.Get("sort[1][direction]"); got != "desc" {
		t.Fatalf("sort[1][direction] = %q, want desc", got)
	}
}

func TestQueryToValuesSortDefaultsToAsc(t *testing.T) {
	q := &Query{Sorts: []Sort{{Field: "Name"}}}
	v := q.toValues("")
	if got := v.Get("sort[0][direction]"); got != "asc" {
		t.Fatalf("empty direction should default to asc, got %q", got)
	}
}

func TestQueryToValuesFields(t *testing.T) {
	q := (&Query{}).WithFields("Name", "Age")
	v := q.toValues("")
	got := v["fields[]"]
	if len(got) != 2 || got[0] != "Name" || got[1] != "Age" {
		t.Fatalf("fields[] = %v, want [Name Age]", got)
	}
}

func TestQueryToValuesMaxRecordsAndPageSize(t *testing.T) {
	q := (&Query{}).WithMaxRecords(100).WithPageSize(50)
	v := q.toValues("")
	if got := v.Get("maxRecords"); got != "100" {
		t.Fatalf("maxRecords = %q, want 100", got)
	}
	if got := v.Get("pageSize"); got != "50" {
		t.Fatalf("pageSize = %q, want 50", got)
	}
}

func TestQueryToValuesZeroMaxRecordsOmitted(t *testing.T) {
	v := (&Query{}).toValues("")
	if _, ok := v["maxRecords"]; ok {
		t.Fatalf("zero maxRecords should be omitted")
	}
	if _, ok := v["pageSize"]; ok {
		t.Fatalf("zero pageSize should be omitted")
	}
}

type fakeView struct{ id string }

func (f fakeView) ViewID() string { return f.id }

func TestQueryToValuesView(t *testing.T) {
	q := (&Query{}).WithView(fakeView{id: "viwABC123"})
	v := q.toValues("")
	if got := v.Get("view"); got != "viwABC123" {
		t.Fatalf("view = %q, want viwABC123", got)
	}
}

func TestQueryToValuesReturnFieldsByFieldID(t *testing.T) {
	q := (&Query{}).WithReturnFieldsByFieldID(true)
	v := q.toValues("")
	if got := v.Get("returnFieldsByFieldId"); got != "true" {
		t.Fatalf("returnFieldsByFieldId = %q, want true", got)
	}

	v2 := (&Query{}).toValues("")
	if _, ok := v2["returnFieldsByFieldId"]; ok {
		t.Fatalf("returnFieldsByFieldId should be omitted when false")
	}
}

func TestQueryToValuesOffset(t *testing.T) {
	v := (&Query{}).toValues("itrCursor/recXYZ")
	if got := v.Get("offset"); got != "itrCursor/recXYZ" {
		t.Fatalf("offset = %q, want itrCursor/recXYZ", got)
	}

	v2 := (&Query{}).toValues("")
	if _, ok := v2["offset"]; ok {
		t.Fatalf("empty offset should be omitted")
	}
}

func TestQueryToValuesNilQuery(t *testing.T) {
	var q *Query
	v := q.toValues("cursor")
	if got := v.Get("offset"); got != "cursor" {
		t.Fatalf("nil query with offset = %q, want cursor", got)
	}

	v2 := q.toValues("")
	if len(v2) != 0 {
		t.Fatalf("nil query no offset should be empty, got %v", v2)
	}
}

func TestQueryCacheKeyStableAndDistinct(t *testing.T) {
	q1 := (&Query{}).WithFilter("{A}=1").WithMaxRecords(10)
	q2 := (&Query{}).WithFilter("{A}=1").WithMaxRecords(10)
	if q1.cacheKey() != q2.cacheKey() {
		t.Fatalf("equal queries should have equal cache keys: %q vs %q", q1.cacheKey(), q2.cacheKey())
	}

	q3 := (&Query{}).WithFilter("{A}=2").WithMaxRecords(10)
	if q1.cacheKey() == q3.cacheKey() {
		t.Fatalf("different filters should produce different cache keys")
	}
}

func TestQueryCacheKeyExcludesOffset(t *testing.T) {
	// cacheKey is toValues("").Encode(); offset must not be part of it.
	q := (&Query{}).WithFilter("{A}=1")
	key := q.cacheKey()
	parsed, err := url.ParseQuery(key)
	if err != nil {
		t.Fatalf("cacheKey not a valid query string: %v", err)
	}
	if _, ok := parsed["offset"]; ok {
		t.Fatalf("cacheKey should not contain offset")
	}
}

func TestQueryCacheKeyNil(t *testing.T) {
	var q *Query
	if got := q.cacheKey(); got != "" {
		t.Fatalf("nil query cacheKey = %q, want empty", got)
	}
}
