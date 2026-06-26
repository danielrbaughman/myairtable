package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Deterministic, hermetic verification of the idempotency-aware retry policy in {@link
 * AirtableClient#send(String, java.net.URI, String, boolean)} (epic follow-up myairtable-rxht, T1).
 *
 * <p>Policy (unified retry spec, child kx1m): a 429 is ALWAYS retried — the request was rejected,
 * so nothing was applied; surfaces {@link AirtableException.RateLimited} only after exhausting
 * {@code maxRetries}. A 5xx is retried ONLY when the request is idempotent
 * (GET/list/get-by-id/update-by- id/delete/upsert-with-merge-fields); a non-idempotent write
 * (create / POST, merge-less upsert) is NOT retried on 5xx — a retried POST could duplicate the
 * records — and the error surfaces on the first attempt.
 *
 * <p>Mechanics: the client accepts an injected {@link java.net.http.HttpClient} (full constructor's
 * last param; {@code null} builds its own). We inject a {@link FakeTransport} — a subclass of
 * {@code HttpClient} that overrides {@code send}/{@code sendAsync} to return scripted {@code
 * HttpResponse} objects keyed off a per-call index and counts every call ({@link
 * FakeTransport#callCount()}). No socket is opened. {@code baseRetryDelaySeconds} and {@code
 * maxRetryDelaySeconds} are pinned to 0 so the retry path never actually sleeps — the assertions
 * are on attempt counts and the terminal exception, not on elapsed time (that timing behavior is
 * covered by {@code TestClientHardening}).
 *
 * <p>Idempotent paths are driven through {@link AirtableClient#listRecords} (GET) and {@link
 * AirtableClient#getRecord} (GET); the non-idempotent path through {@link
 * AirtableClient#createRecords} (POST, hard-wired to {@code idempotent=false}).
 */
class TestClientRetryPolicy {

  private static final String OK_LIST = "{\"records\": []}";
  private static final String OK_RECORD = "{\"id\": \"recX\", \"fields\": {}}";
  private static final String OK_CREATE = "{\"records\": [{\"id\": \"recNew\", \"fields\": {}}]}";

  /** A 503 SERVICE_UNAVAILABLE error envelope (a representative retryable 5xx). */
  private static FakeTransport.Canned serviceUnavailable() {
    return new FakeTransport.Canned(
        503,
        "{\"error\": {\"type\": \"SERVICE_UNAVAILABLE\", \"message\": \"try again\"}}",
        Map.of("Content-Type", List.of("application/json")));
  }

  /** A 429 RATE_LIMITED error envelope. */
  private static FakeTransport.Canned rateLimited() {
    return new FakeTransport.Canned(
        429,
        "{\"error\": {\"type\": \"RATE_LIMITED\", \"message\": \"slow down\"}}",
        Map.of("Content-Type", List.of("application/json")));
  }

  /**
   * Client over the given fake transport with zero retry delay (no real sleeping) and {@code
   * maxRetries=3}, the production default.
   */
  private static AirtableClient client(FakeTransport transport) {
    return client(transport, 3);
  }

  private static AirtableClient client(FakeTransport transport, int maxRetries) {
    return new AirtableClient(
        "appX",
        "key",
        "https://api.airtable.com/v0",
        new CacheStore(),
        maxRetries,
        0.0, // baseRetryDelaySeconds — 0 so Thread.sleep is a no-op
        0.0, // maxRetryDelaySeconds — 0 so any Retry-After is capped to 0 too
        30.0,
        transport);
  }

  // ---- 1. idempotent GET: 503 twice, then 200 → 3 attempts, succeeds ----

  @Test
  void idempotentGetRetries503ThenSucceeds() {
    FakeTransport transport =
        new FakeTransport(
            (request, callIndex) ->
                callIndex < 2 ? serviceUnavailable() : FakeTransport.Canned.ok(OK_LIST));
    AirtableClient client = client(transport);

    String payload = client.listRecords("tbl1", new AirtableQuery());

    assertEquals(OK_LIST, payload, "the 3rd attempt's 200 body must be returned");
    assertEquals(3, transport.callCount(), "two 503s should be retried, succeeding on attempt 3");
  }

  // ---- 2. idempotent op: 503 persistently → maxRetries+1 attempts, then throws ----

  @Test
  void idempotentOpExhaustsRetriesOnPersistent503() {
    int maxRetries = 3;
    FakeTransport transport = new FakeTransport((request, callIndex) -> serviceUnavailable());
    AirtableClient client = client(transport, maxRetries);

    AirtableException err =
        assertThrows(
            AirtableException.class,
            () -> client.getRecord("tbl1", "recX"),
            "a persistent 503 must surface after retries are exhausted");

    // 1 initial attempt + maxRetries retries.
    assertEquals(
        maxRetries + 1,
        transport.callCount(),
        "idempotent 5xx should be attempted maxRetries+1 times");
    // The structured 503 envelope decodes to a typed Api error carrying the code.
    AirtableException.Api api =
        assertInstanceOf(
            AirtableException.Api.class, err, "the decoded 503 envelope must be a typed Api error");
    assertEquals("SERVICE_UNAVAILABLE", api.code());
  }

  // ---- 3. NON-idempotent createRecords (POST): 503 → exactly 1 attempt, throws immediately ----

  @Test
  void nonIdempotentCreateDoesNotRetryOn503() {
    FakeTransport transport = new FakeTransport((request, callIndex) -> serviceUnavailable());
    AirtableClient client = client(transport);

    assertThrows(
        AirtableException.class,
        () -> client.createRecords("tbl1", OK_CREATE),
        "a 5xx on a non-idempotent POST must surface immediately");

    assertEquals(
        1,
        transport.callCount(),
        "createRecords (POST) is not idempotent — a 5xx must NOT be retried");
  }

  // ---- 4. 429 then 200 on ANY op → retried (2 attempts) ----

  @Test
  void rateLimitedIsRetriedEvenOnNonIdempotentOp() {
    // 429 means the request was rejected (nothing applied), so it is always
    // retryable — even for the non-idempotent create path.
    FakeTransport transport =
        new FakeTransport(
            (request, callIndex) ->
                callIndex < 1 ? rateLimited() : FakeTransport.Canned.ok(OK_CREATE));
    AirtableClient client = client(transport);

    String payload = client.createRecords("tbl1", OK_CREATE);

    assertEquals(OK_CREATE, payload, "the retry's 200 body must be returned");
    assertEquals(2, transport.callCount(), "a 429 is retried regardless of idempotency");
  }

  @Test
  void rateLimitedIsRetriedOnIdempotentOp() {
    FakeTransport transport =
        new FakeTransport(
            (request, callIndex) ->
                callIndex < 1 ? rateLimited() : FakeTransport.Canned.ok(OK_LIST));
    AirtableClient client = client(transport);

    String payload = client.listRecords("tbl1", new AirtableQuery());

    assertEquals(OK_LIST, payload);
    assertEquals(2, transport.callCount(), "a 429 then 200 is exactly two attempts");
  }

  // ---- terminal 429 surfaces RateLimited after exhausting retries ----

  @Test
  void persistent429SurfacesRateLimitedAfterMaxRetries() {
    int maxRetries = 2;
    FakeTransport transport = new FakeTransport((request, callIndex) -> rateLimited());
    AirtableClient client = client(transport, maxRetries);

    assertThrows(
        AirtableException.RateLimited.class,
        () -> client.listRecords("tbl1", new AirtableQuery()),
        "a persistent 429 must surface as RateLimited once retries are exhausted");

    assertEquals(
        maxRetries + 1, transport.callCount(), "429 should be attempted maxRetries+1 times");
  }
}
