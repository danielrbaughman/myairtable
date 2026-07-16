package airtable

// Pointer-helper constructors for building models with optional (pointer)
// fields via struct literals — the idiomatic Go creation path (AWS-SDK style):
//
//	p := PrimaryModel{PrimaryKey: airtable.String("x")}

import "time"

// String returns a pointer to s.
func String(s string) *string { return &s }

// Float64 returns a pointer to f.
func Float64(f float64) *float64 { return &f }

// Int64 returns a pointer to i.
func Int64(i int64) *int64 { return &i }

// Bool returns a pointer to b.
func Bool(b bool) *bool { return &b }

// Time wraps t as a *AirtableTime.
func Time(t time.Time) *AirtableTime { return &AirtableTime{Time: t} }

// Duration wraps d as a *AirtableDuration.
func Duration(d time.Duration) *AirtableDuration {
	ad := AirtableDuration(d)
	return &ad
}
