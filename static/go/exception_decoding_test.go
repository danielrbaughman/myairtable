package airtable

// White-box tests for errorFromResponse and the typed error model. Mirrors the
// Java TestAirtableExceptionDecoding cases adapted to the Go error API.

import (
	"errors"
	"testing"
)

func TestErrorFromResponseObjectForm(t *testing.T) {
	body := []byte(`{"error":{"type":"INVALID_REQUEST","message":"bad filter"}}`)
	err := errorFromResponse(422, body)

	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected *APIError, got %T: %v", err, err)
	}
	if apiErr.StatusCode != 422 {
		t.Fatalf("StatusCode = %d, want 422", apiErr.StatusCode)
	}
	if apiErr.Type != "INVALID_REQUEST" {
		t.Fatalf("Type = %q, want INVALID_REQUEST", apiErr.Type)
	}
	if apiErr.Message != "bad filter" {
		t.Fatalf("Message = %q, want bad filter", apiErr.Message)
	}
}

func TestErrorFromResponseBareStringForm(t *testing.T) {
	body := []byte(`{"error":"NOT_FOUND"}`)
	err := errorFromResponse(404, body)

	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected *APIError, got %T: %v", err, err)
	}
	if apiErr.StatusCode != 404 {
		t.Fatalf("StatusCode = %d, want 404", apiErr.StatusCode)
	}
	if apiErr.Type != "NOT_FOUND" || apiErr.Message != "NOT_FOUND" {
		t.Fatalf("Type/Message = %q/%q, want NOT_FOUND/NOT_FOUND", apiErr.Type, apiErr.Message)
	}
}

func TestErrorFromResponseNonJSON(t *testing.T) {
	body := []byte(`<html>502 Bad Gateway</html>`)
	err := errorFromResponse(502, body)

	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected *HTTPError, got %T: %v", err, err)
	}
	if httpErr.StatusCode != 502 {
		t.Fatalf("StatusCode = %d, want 502", httpErr.StatusCode)
	}
	if httpErr.Body != "<html>502 Bad Gateway</html>" {
		t.Fatalf("Body = %q", httpErr.Body)
	}
}

func TestErrorFromResponseJSONWithoutErrorEnvelope(t *testing.T) {
	// Valid JSON but no "error" key -> falls back to HTTPError.
	body := []byte(`{"something":"else"}`)
	err := errorFromResponse(500, body)

	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("expected *HTTPError, got %T: %v", err, err)
	}
}

func TestErrorIsNotFoundForAPIError404(t *testing.T) {
	err := errorFromResponse(404, []byte(`{"error":"NOT_FOUND"}`))
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("errors.Is(err, ErrNotFound) should be true for 404 APIError")
	}
}

func TestErrorIsNotFoundForHTTPError404(t *testing.T) {
	err := errorFromResponse(404, []byte(`not json`))
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("errors.Is(err, ErrNotFound) should be true for 404 HTTPError")
	}
}

func TestErrorIsNotNotFoundForNon404(t *testing.T) {
	err := errorFromResponse(422, []byte(`{"error":{"type":"INVALID","message":"x"}}`))
	if errors.Is(err, ErrNotFound) {
		t.Fatalf("errors.Is(err, ErrNotFound) should be false for 422")
	}
}

func TestErrorsAsRateLimitError(t *testing.T) {
	var rl error = &RateLimitError{RetryAfter: 0}
	var target *RateLimitError
	if !errors.As(rl, &target) {
		t.Fatalf("errors.As should match *RateLimitError")
	}
}

func TestDecodingErrorUnwrap(t *testing.T) {
	cause := errors.New("boom")
	de := &DecodingError{Err: cause}
	if !errors.Is(de, cause) {
		t.Fatalf("errors.Is should reach the wrapped cause via Unwrap")
	}
	if de.Unwrap() != cause {
		t.Fatalf("Unwrap() should return the cause")
	}
}

func TestAPIErrorMessageFormatting(t *testing.T) {
	withType := &APIError{StatusCode: 404, Type: "NOT_FOUND", Message: "gone"}
	if withType.Error() != "airtable: API error 404: NOT_FOUND: gone" {
		t.Fatalf("unexpected Error(): %q", withType.Error())
	}
	noType := &APIError{StatusCode: 500, Message: "boom"}
	if noType.Error() != "airtable: API error 500: boom" {
		t.Fatalf("unexpected Error(): %q", noType.Error())
	}
}
