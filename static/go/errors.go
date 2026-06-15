package airtable

// Error model: errors are returned, never panicked. Callers use errors.Is for
// the sentinels and errors.As for the typed errors (which carry structured
// fields like StatusCode / RetryAfter).

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// Sentinel errors — compare with errors.Is.
var (
	// ErrNotFound is returned (wrapped) when a record or resource does not exist.
	ErrNotFound = errors.New("airtable: not found")
	// ErrMissingCredentials is returned when the API key or base ID is unset.
	ErrMissingCredentials = errors.New("airtable: missing credentials")
)

// APIError is a structured Airtable API error (4xx/5xx with a JSON error body).
// Inspect with errors.As.
type APIError struct {
	StatusCode int
	Type       string
	Message    string
}

func (e *APIError) Error() string {
	if e.Type != "" {
		return fmt.Sprintf("airtable: API error %d: %s: %s", e.StatusCode, e.Type, e.Message)
	}
	return fmt.Sprintf("airtable: API error %d: %s", e.StatusCode, e.Message)
}

// Is lets errors.Is(err, ErrNotFound) succeed for 404 API errors.
func (e *APIError) Is(target error) bool {
	return target == ErrNotFound && e.StatusCode == 404
}

// RateLimitError is returned on HTTP 429 once retries are exhausted. RetryAfter
// is the suggested wait before retrying.
type RateLimitError struct {
	RetryAfter time.Duration
}

func (e *RateLimitError) Error() string {
	return fmt.Sprintf("airtable: rate limited (retry after %s)", e.RetryAfter)
}

// HTTPError is returned for non-JSON or otherwise unstructured HTTP failures.
type HTTPError struct {
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("airtable: HTTP %d: %s", e.StatusCode, e.Body)
}

func (e *HTTPError) Is(target error) bool {
	return target == ErrNotFound && e.StatusCode == 404
}

// DecodingError wraps a JSON (un)marshaling failure. Unwrap exposes the cause.
type DecodingError struct {
	Err error
}

func (e *DecodingError) Error() string { return "airtable: decoding error: " + e.Err.Error() }
func (e *DecodingError) Unwrap() error { return e.Err }

// errorEnvelope is the Airtable wire error body. The "error" field is either a
// bare string (e.g. "NOT_FOUND") or an object {type, message}.
type errorEnvelope struct {
	Error json.RawMessage `json:"error"`
}

// errorFromResponse converts an HTTP status + body into a typed error. It
// returns *APIError when the body carries an Airtable error envelope, otherwise
// *HTTPError.
func errorFromResponse(status int, body []byte) error {
	var env errorEnvelope
	if err := json.Unmarshal(body, &env); err == nil && len(env.Error) > 0 {
		// Try object form first: {"type": "...", "message": "..."}.
		var obj struct {
			Type    string `json:"type"`
			Message string `json:"message"`
		}
		if err := json.Unmarshal(env.Error, &obj); err == nil && (obj.Type != "" || obj.Message != "") {
			return &APIError{StatusCode: status, Type: obj.Type, Message: obj.Message}
		}
		// Fall back to bare-string form: {"error": "NOT_FOUND"}.
		var msg string
		if err := json.Unmarshal(env.Error, &msg); err == nil {
			return &APIError{StatusCode: status, Type: msg, Message: msg}
		}
	}
	return &HTTPError{StatusCode: status, Body: string(body)}
}
