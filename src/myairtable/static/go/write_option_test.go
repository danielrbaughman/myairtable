package airtable

// Tests for the WithTypecast write option (myairtable-hbph). They install a
// scripted RoundTripper (same pattern as client_retry_hermetic_test.go and
// table_bounded_ops_test.go) that captures the raw request body, then assert
// the body carries "typecast":true exactly when WithTypecast() is passed and
// omits it by default — across create / update / upsert on both Table and
// DictTable.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

// bodyCapturingTransport records the raw request body of each write and replies
// with a canned 200 that echoes one synthetic record per input record so the
// create/update/upsert decode paths succeed.
type bodyCapturingTransport struct {
	bodies []string
}

func (rt *bodyCapturingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	var raw []byte
	if req.Body != nil {
		raw, _ = io.ReadAll(req.Body)
	}
	rt.bodies = append(rt.bodies, string(raw))

	var parsed struct {
		Records []json.RawMessage `json:"records"`
	}
	_ = json.Unmarshal(raw, &parsed)
	respRecords := make([]map[string]any, 0, len(parsed.Records))
	for i := range parsed.Records {
		respRecords = append(respRecords, map[string]any{
			"id":     "rec" + strings.Repeat("X", i+1),
			"fields": map[string]any{},
		})
	}
	out, _ := json.Marshal(map[string]any{"records": respRecords})
	return cannedResponse(string(out)), nil
}

func (rt *bodyCapturingTransport) last() string {
	if len(rt.bodies) == 0 {
		return ""
	}
	return rt.bodies[len(rt.bodies)-1]
}

func assertTypecast(t *testing.T, body string, want bool) {
	t.Helper()
	has := strings.Contains(body, `"typecast":true`)
	if has != want {
		t.Fatalf("typecast presence = %v, want %v; body=%s", has, want, body)
	}
}

func TestWriteOption_DictTableCreate(t *testing.T) {
	fields := func() *Fields {
		return NewFields(map[string]json.RawMessage{"fldA": json.RawMessage(`"v"`)}, nil)
	}

	t.Run("default omits typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
		if _, err := tbl.CreateOne(context.Background(), fields()); err != nil {
			t.Fatalf("CreateOne: %v", err)
		}
		assertTypecast(t, rt.last(), false)
	})

	t.Run("WithTypecast sets typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
		if _, err := tbl.CreateOne(context.Background(), fields(), WithTypecast()); err != nil {
			t.Fatalf("CreateOne: %v", err)
		}
		assertTypecast(t, rt.last(), true)
	})
}

func TestWriteOption_DictTableUpdate(t *testing.T) {
	fields := func() *Fields {
		return NewFields(map[string]json.RawMessage{"fldA": json.RawMessage(`"v"`)}, nil)
	}

	t.Run("default omits typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
		if _, err := tbl.UpdateOne(context.Background(), "rec1", fields()); err != nil {
			t.Fatalf("UpdateOne: %v", err)
		}
		assertTypecast(t, rt.last(), false)
	})

	t.Run("WithTypecast sets typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewDictTable(clientWithTransport(rt), "tblStub", nil)
		if _, err := tbl.UpdateOne(context.Background(), "rec1", fields(), WithTypecast()); err != nil {
			t.Fatalf("UpdateOne: %v", err)
		}
		assertTypecast(t, rt.last(), true)
	})
}

func TestWriteOption_TableCreateMany(t *testing.T) {
	t.Run("default omits typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewTable[revModel, *revModel](clientWithTransport(rt), "tblRev", nil)
		if _, err := tbl.CreateMany(context.Background(), []*revModel{{Name: String("a")}}); err != nil {
			t.Fatalf("CreateMany: %v", err)
		}
		assertTypecast(t, rt.last(), false)
	})

	t.Run("WithTypecast sets typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewTable[revModel, *revModel](clientWithTransport(rt), "tblRev", nil)
		if _, err := tbl.CreateMany(context.Background(), []*revModel{{Name: String("a")}}, WithTypecast()); err != nil {
			t.Fatalf("CreateMany: %v", err)
		}
		assertTypecast(t, rt.last(), true)
	})
}

func TestWriteOption_TableUpsert(t *testing.T) {
	t.Run("default omits typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewTable[revModel, *revModel](clientWithTransport(rt), "tblRev", nil)
		m := &revModel{Name: String("a")}
		if _, err := tbl.Upsert(context.Background(), m, []string{"fldName"}); err != nil {
			t.Fatalf("Upsert: %v", err)
		}
		assertTypecast(t, rt.last(), false)
	})

	t.Run("WithTypecast sets typecast", func(t *testing.T) {
		rt := &bodyCapturingTransport{}
		tbl := NewTable[revModel, *revModel](clientWithTransport(rt), "tblRev", nil)
		m := &revModel{Name: String("a")}
		if _, err := tbl.Upsert(context.Background(), m, []string{"fldName"}, WithTypecast()); err != nil {
			t.Fatalf("Upsert: %v", err)
		}
		assertTypecast(t, rt.last(), true)
	})
}
