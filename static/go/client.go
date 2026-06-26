package airtable

// Client is the low-level Airtable REST client: bearer auth, context-aware 429
// retry/backoff, record CRUD with chunk-of-10 batching, and a TTL read cache.
// Higher-level typed/dict tables (table.go, dict_table.go) build on it.
//
// URL encoding: query parameters are rendered with url.Values.Encode(), which
// encodes '+' as %2B and ' ' as '+'. Airtable decodes those back correctly, so
// formulas like LEN({f})+1 round-trip (unlike the raw-'+' bug seen with some
// other HTTP stacks). Path segments use url.PathEscape. Pinned by the live URL
// round-trip test.

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	apiBaseURL       = "https://api.airtable.com/v0"
	maxBatch         = 10
	maxRetries       = 5
	defaultRetryWait = 30 * time.Second
)

// Retry backoff timing — vars (not consts) so tests can shrink the delays.
var (
	retryBaseDelay = 1 * time.Second
	maxRetryWait   = 30 * time.Second
)

// Client is the Airtable API client. Construct with NewClient.
type Client struct {
	apiKey     string
	baseID     string
	httpClient *http.Client
	cache      *cacheStore
}

// NewClient builds a Client. cacheSeconds <= 0 disables read caching.
func NewClient(apiKey, baseID string, cacheSeconds float64) *Client {
	var cache *cacheStore
	if cacheSeconds > 0 {
		cache = newCacheStore(time.Duration(cacheSeconds * float64(time.Second)))
	}
	return &Client{
		apiKey:     apiKey,
		baseID:     baseID,
		httpClient: &http.Client{Timeout: 60 * time.Second},
		cache:      cache,
	}
}

// BaseID returns the configured base ID.
func (c *Client) BaseID() string { return c.baseID }

// InvalidateAllCaches clears all cached reads.
func (c *Client) InvalidateAllCaches() { c.cache.invalidateAll() }

// InvalidateTableCache clears cached reads for one table.
func (c *Client) InvalidateTableCache(tableID string) { c.cache.invalidateTable(tableID) }

type rawRecord struct {
	ID          string          `json:"id"`
	CreatedTime *AirtableTime   `json:"createdTime,omitempty"`
	Fields      json.RawMessage `json:"fields"`
}

type recordPayload struct {
	ID     string                     `json:"id,omitempty"`
	Fields map[string]json.RawMessage `json:"fields"`
}

func (c *Client) recordURL(tableID, recordID string, query url.Values) string {
	var b strings.Builder
	b.WriteString(apiBaseURL)
	b.WriteString("/")
	b.WriteString(url.PathEscape(c.baseID))
	b.WriteString("/")
	b.WriteString(url.PathEscape(tableID))
	if recordID != "" {
		b.WriteString("/")
		b.WriteString(url.PathEscape(recordID))
	}
	if len(query) > 0 {
		b.WriteString("?")
		b.WriteString(query.Encode())
	}
	return b.String()
}

// do performs an HTTP request with bearer auth and 429/5xx retry with jittered
// backoff (honoring a server Retry-After). It returns
// the response body for 2xx, or a typed error otherwise.
//
// The idempotent flag controls which failures are retried. A 429 is ALWAYS
// retried (the server rejected the request; nothing was applied). A 5xx or a
// transport/IO error is retried ONLY IF idempotent — otherwise it returns
// immediately, since a non-idempotent op (e.g. create POST) may have been
// applied server-side even though the response failed. We deliberately do NOT
// try to distinguish a connect-before-send failure from a read-timeout: that is
// not portably available, and the conservative uniform rule is correct.
func (c *Client) do(ctx context.Context, method, fullURL string, body []byte, idempotent bool) ([]byte, error) {
	if c.apiKey == "" || c.baseID == "" {
		return nil, ErrMissingCredentials
	}

	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		var reqBody io.Reader
		if body != nil {
			reqBody = bytes.NewReader(body)
		}
		req, err := http.NewRequestWithContext(ctx, method, fullURL, reqBody)
		if err != nil {
			return nil, &DecodingError{Err: err}
		}
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
		if body != nil {
			req.Header.Set("Content-Type", "application/json")
		}

		resp, err := c.httpClient.Do(req)
		if err != nil {
			// Transport/IO error: retry only if idempotent, else surface it now.
			if !idempotent {
				return nil, err
			}
			lastErr = err
			if attempt < maxRetries {
				select {
				case <-ctx.Done():
					return nil, ctx.Err()
				case <-time.After(retryWait(attempt, 0)):
				}
				continue
			}
			break
		}
		respBody, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			return nil, readErr
		}

		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return respBody, nil
		}
		// 429 is always transient; 5xx is transient only for idempotent ops.
		// Every other 4xx fails immediately.
		if resp.StatusCode != 429 && resp.StatusCode < 500 {
			return nil, errorFromResponse(resp.StatusCode, respBody)
		}

		var retryAfter time.Duration
		if resp.StatusCode == 429 {
			retryAfter = parseRetryAfter(resp.Header.Get("Retry-After"))
			reported := retryAfter
			if reported == 0 {
				reported = defaultRetryWait
			}
			lastErr = &RateLimitError{RetryAfter: reported}
		} else {
			// 5xx
			lastErr = errorFromResponse(resp.StatusCode, respBody)
			if !idempotent {
				return nil, lastErr
			}
		}

		if attempt < maxRetries {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(retryWait(attempt, retryAfter)):
			}
			continue
		}
	}
	return nil, lastErr
}

// parseRetryAfter parses a Retry-After header value per RFC 9110. It accepts
// either delta-seconds ("120") or an HTTP-date ("Wed, 21 Oct 2015 07:28:00
// GMT"); for the date form it returns max(0, date-now). A garbage or negative
// value floors to 0 (never returns a negative duration).
func parseRetryAfter(ra string) time.Duration {
	if ra == "" {
		return 0
	}
	if secs, err := strconv.Atoi(strings.TrimSpace(ra)); err == nil {
		if secs < 0 {
			return 0
		}
		return time.Duration(secs) * time.Second
	}
	if t, err := http.ParseTime(strings.TrimSpace(ra)); err == nil {
		d := time.Until(t)
		if d < 0 {
			return 0
		}
		return d
	}
	return 0
}

// retryWait computes the delay before the next retry. An explicit server
// Retry-After is honored as a floor (plus small jitter); otherwise an
// exponential backoff with decorrelated jitter is used to avoid a thundering
// herd. The final delay — for BOTH paths — is capped at maxRetryWait, so a
// broken/malicious Retry-After (e.g. "999999") can never hang the call.
func retryWait(attempt int, retryAfter time.Duration) time.Duration {
	var d time.Duration
	if retryAfter > 0 {
		if retryAfter > maxRetryWait {
			retryAfter = maxRetryWait
		}
		d = retryAfter + jitter(retryAfter/4)
	} else {
		base := retryBaseDelay << uint(attempt)
		if base > maxRetryWait {
			base = maxRetryWait
		}
		d = base + jitter(base/2)
	}
	if d > maxRetryWait {
		d = maxRetryWait
	}
	return d
}

// jitter returns a random duration in [0, max). The global rand source is
// auto-seeded (Go 1.20+); concurrency-safe.
func jitter(max time.Duration) time.Duration {
	if max <= 0 {
		return 0
	}
	return time.Duration(rand.Int63n(int64(max)))
}

// getRecord fetches a single record by ID (fields keyed by field ID).
func (c *Client) getRecord(ctx context.Context, tableID, recordID string) (*rawRecord, error) {
	q := url.Values{}
	q.Set("returnFieldsByFieldId", "true")
	cacheKey := "rec:" + recordID
	if data, ok := c.cache.get(tableID, cacheKey); ok {
		var rec rawRecord
		if err := json.Unmarshal(data, &rec); err != nil {
			return nil, &DecodingError{Err: err}
		}
		return &rec, nil
	}
	data, err := c.do(ctx, http.MethodGet, c.recordURL(tableID, recordID, q), nil, true)
	if err != nil {
		return nil, err
	}
	var rec rawRecord
	if err := json.Unmarshal(data, &rec); err != nil {
		return nil, &DecodingError{Err: err}
	}
	c.cache.set(tableID, cacheKey, data)
	return &rec, nil
}

type listResponse struct {
	Records []rawRecord `json:"records"`
	Offset  string      `json:"offset"`
}

// listRecords fetches all records matching the query, following pagination.
func (c *Client) listRecords(ctx context.Context, tableID string, q *Query) ([]rawRecord, error) {
	effective := q
	if effective == nil {
		effective = &Query{}
	}
	effective.ReturnFieldsByFieldID = true

	cacheKey := "list:" + effective.cacheKey()
	if data, ok := c.cache.get(tableID, cacheKey); ok {
		var recs []rawRecord
		if err := json.Unmarshal(data, &recs); err != nil {
			return nil, &DecodingError{Err: err}
		}
		return recs, nil
	}

	var all []rawRecord
	offset := ""
	for {
		values := effective.toValues(offset)
		data, err := c.do(ctx, http.MethodGet, c.recordURL(tableID, "", values), nil, true)
		if err != nil {
			return nil, err
		}
		var page listResponse
		if err := json.Unmarshal(data, &page); err != nil {
			return nil, &DecodingError{Err: err}
		}
		all = append(all, page.Records...)
		if page.Offset == "" || (effective.MaxRecords > 0 && len(all) >= effective.MaxRecords) {
			break
		}
		offset = page.Offset
	}

	if cached, err := json.Marshal(all); err == nil {
		c.cache.set(tableID, cacheKey, cached)
	}
	return all, nil
}

// createRecords creates records in chunks of 10, returning the created records.
func (c *Client) createRecords(ctx context.Context, tableID string, fields []map[string]json.RawMessage, typecast bool) ([]rawRecord, error) {
	var created []rawRecord
	for start := 0; start < len(fields); start += maxBatch {
		end := min(start+maxBatch, len(fields))
		payload := make([]recordPayload, 0, end-start)
		for _, f := range fields[start:end] {
			payload = append(payload, recordPayload{Fields: f})
		}
		// create = POST = non-idempotent: do not retry 5xx/transport errors.
		recs, err := c.writeBatch(ctx, http.MethodPost, tableID, payload, typecast, false)
		if err != nil {
			return nil, err
		}
		created = append(created, recs...)
	}
	c.cache.invalidateTable(tableID)
	return created, nil
}

// updateRecords PATCHes records in chunks of 10, returning the updated records.
func (c *Client) updateRecords(ctx context.Context, tableID string, updates []recordPayload, typecast bool) ([]rawRecord, error) {
	var updated []rawRecord
	for start := 0; start < len(updates); start += maxBatch {
		end := min(start+maxBatch, len(updates))
		// update-by-id = PATCH with record IDs = idempotent.
		recs, err := c.writeBatch(ctx, http.MethodPatch, tableID, updates[start:end], typecast, true)
		if err != nil {
			return nil, err
		}
		updated = append(updated, recs...)
	}
	c.cache.invalidateTable(tableID)
	return updated, nil
}

// upsertRecords PATCHes records with performUpsert, matching on fieldsToMergeOn.
func (c *Client) upsertRecords(ctx context.Context, tableID string, records []recordPayload, matchFields []string) ([]rawRecord, error) {
	reqBody := map[string]any{
		"records":               records,
		"returnFieldsByFieldId": true,
		"performUpsert":         map[string]any{"fieldsToMergeOn": matchFields},
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, &DecodingError{Err: err}
	}
	// Upsert is idempotent only when a merge key identifies records; with no
	// fieldsToMergeOn it inserts (like create) and must not retry 5xx/transport.
	idempotent := len(matchFields) > 0
	data, err := c.do(ctx, http.MethodPatch, c.recordURL(tableID, "", nil), body, idempotent)
	if err != nil {
		return nil, err
	}
	var resp listResponse
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, &DecodingError{Err: err}
	}
	c.cache.invalidateTable(tableID)
	return resp.Records, nil
}

func (c *Client) writeBatch(ctx context.Context, method, tableID string, records []recordPayload, typecast, idempotent bool) ([]rawRecord, error) {
	reqBody := map[string]any{"records": records, "returnFieldsByFieldId": true}
	if typecast {
		reqBody["typecast"] = true
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, &DecodingError{Err: err}
	}
	data, err := c.do(ctx, method, c.recordURL(tableID, "", nil), body, idempotent)
	if err != nil {
		return nil, err
	}
	var resp listResponse
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, &DecodingError{Err: err}
	}
	return resp.Records, nil
}

// deleteRecords deletes records in chunks of 10.
func (c *Client) deleteRecords(ctx context.Context, tableID string, ids []string) error {
	for start := 0; start < len(ids); start += maxBatch {
		end := min(start+maxBatch, len(ids))
		q := url.Values{}
		for _, id := range ids[start:end] {
			q.Add("records[]", id)
		}
		if _, err := c.do(ctx, http.MethodDelete, c.recordURL(tableID, "", q), nil, true); err != nil {
			return err
		}
	}
	c.cache.invalidateTable(tableID)
	return nil
}
