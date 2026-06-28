package airtable

// WriteOption configures a single create/update/upsert call. Options are passed
// variadically so existing callers (which pass none) keep working unchanged and
// the default behavior is preserved.
type WriteOption func(*writeOptions)

// writeOptions is the resolved set of per-write settings. Its zero value is the
// default (typecast disabled), matching pre-option behavior.
type writeOptions struct {
	typecast bool
}

// WithTypecast enables Airtable's per-request typecast: when set, Airtable
// coerces string inputs to each cell's type (parsing dates/numbers, creating
// missing select options, etc.). Default is off.
func WithTypecast() WriteOption {
	return func(o *writeOptions) { o.typecast = true }
}

// resolveWriteOptions folds the variadic options into a writeOptions value.
func resolveWriteOptions(opts []WriteOption) writeOptions {
	var o writeOptions
	for _, opt := range opts {
		if opt != nil {
			opt(&o)
		}
	}
	return o
}
