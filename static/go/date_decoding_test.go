package airtable

// White-box tests for AirtableTime and AirtableDuration JSON codecs. Mirrors the
// Java TestDateDecoding cases adapted to the Go API.

import (
	"encoding/json"
	"testing"
	"time"
)

func TestAirtableTimeFractionalRFC3339(t *testing.T) {
	var at AirtableTime
	if err := json.Unmarshal([]byte(`"2023-01-15T08:30:00.123Z"`), &at); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	want := time.Date(2023, 1, 15, 8, 30, 0, 123000000, time.UTC)
	if !at.Time.Equal(want) {
		t.Fatalf("got %v, want %v", at.Time, want)
	}
}

func TestAirtableTimePlainRFC3339(t *testing.T) {
	var at AirtableTime
	if err := json.Unmarshal([]byte(`"2023-01-15T08:30:00Z"`), &at); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	want := time.Date(2023, 1, 15, 8, 30, 0, 0, time.UTC)
	if !at.Time.Equal(want) {
		t.Fatalf("got %v, want %v", at.Time, want)
	}
}

func TestAirtableTimeDateOnlyMidnightUTC(t *testing.T) {
	var at AirtableTime
	if err := json.Unmarshal([]byte(`"2023-01-15"`), &at); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	want := time.Date(2023, 1, 15, 0, 0, 0, 0, time.UTC)
	if !at.Time.Equal(want) {
		t.Fatalf("got %v, want %v", at.Time, want)
	}
}

func TestAirtableTimeNormalizesToUTC(t *testing.T) {
	var at AirtableTime
	if err := json.Unmarshal([]byte(`"2023-01-15T08:30:00+02:00"`), &at); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if at.Time.Location() != time.UTC {
		t.Fatalf("expected UTC location, got %v", at.Time.Location())
	}
	want := time.Date(2023, 1, 15, 6, 30, 0, 0, time.UTC)
	if !at.Time.Equal(want) {
		t.Fatalf("got %v, want %v", at.Time, want)
	}
}

func TestAirtableTimeNull(t *testing.T) {
	var at AirtableTime
	if err := json.Unmarshal([]byte(`null`), &at); err != nil {
		t.Fatalf("null should not error: %v", err)
	}
	if !at.Time.IsZero() {
		t.Fatalf("null should leave zero time, got %v", at.Time)
	}
}

func TestAirtableTimeInvalid(t *testing.T) {
	var at AirtableTime
	err := json.Unmarshal([]byte(`"not-a-date"`), &at)
	if err == nil {
		t.Fatalf("invalid date should error")
	}
}

func TestAirtableTimeMarshalRoundTrip(t *testing.T) {
	orig := AirtableTime{Time: time.Date(2023, 1, 15, 8, 30, 0, 0, time.UTC)}
	b, err := json.Marshal(orig)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(b) != `"2023-01-15T08:30:00Z"` {
		t.Fatalf("marshal = %s", b)
	}
	var back AirtableTime
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatalf("unmarshal back: %v", err)
	}
	if !back.Time.Equal(orig.Time) {
		t.Fatalf("round trip mismatch: %v vs %v", back.Time, orig.Time)
	}
}

func TestAirtableDurationEncode(t *testing.T) {
	d := AirtableDuration(30 * time.Second)
	b, err := json.Marshal(d)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(b) != "30" {
		t.Fatalf("30s should encode as \"30\", got %s", b)
	}
}

func TestAirtableDurationDecode(t *testing.T) {
	var d AirtableDuration
	if err := json.Unmarshal([]byte("90"), &d); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if d.Duration() != 90*time.Second {
		t.Fatalf("got %v, want 90s", d.Duration())
	}
}

func TestAirtableDurationFractionalRoundTrip(t *testing.T) {
	var d AirtableDuration
	if err := json.Unmarshal([]byte("1.5"), &d); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if d.Duration() != 1500*time.Millisecond {
		t.Fatalf("got %v, want 1.5s", d.Duration())
	}
	b, err := json.Marshal(d)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(b) != "1.5" {
		t.Fatalf("got %s, want 1.5", b)
	}
}

func TestAirtableDurationNull(t *testing.T) {
	var d AirtableDuration
	if err := json.Unmarshal([]byte("null"), &d); err != nil {
		t.Fatalf("null should not error: %v", err)
	}
	if d.Duration() != 0 {
		t.Fatalf("null should leave zero duration, got %v", d.Duration())
	}
}

func TestAirtableDurationInvalid(t *testing.T) {
	var d AirtableDuration
	if err := json.Unmarshal([]byte(`"abc"`), &d); err == nil {
		t.Fatalf("non-numeric duration should error")
	}
}
