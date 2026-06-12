package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin myairtable-jz87 (TestClientHardening.kt) — close() ownership, retry/backoff,
 * Retry-After cap / HTTP-date handling, transport-error wrapping, and credential validation.
 *
 * <p>Adaptation notes vs the Kotlin twin:
 *
 * <ul>
 *   <li>Ktor's {@code MockEngine} becomes {@link FakeTransport}; {@code runTest}'s virtual clock
 *       has no JDK equivalent, so waits are real ({@code Thread.sleep}) with tiny delays. Exact
 *       virtual-time equalities become discriminating real-clock bounds: a lower bound proves the
 *       wait happened; regressions to the wrong path are caught by configuring the alternative
 *       (jittered backoff) to be multiple seconds and asserting the elapsed time stayed far below.
 *   <li>{@code closeClosesOwnedEngine}: Kotlin asserts the closed-engine failure is NOT {@code
 *       Network}; the JDK HttpClient throws {@code IOException("closed")} after {@code close()},
 *       which the runtime wraps as {@link AirtableException.Network}. The closed-engine failure is
 *       instead distinguished from a live connection attempt by its cause message ({@code
 *       "closed"}, not a connection-refused error).
 * </ul>
 */
class TestClientHardening {

  private static final String OK_BODY = "{\"records\": []}";

  private static AirtableClient client(
      FakeTransport transport,
      int maxRetries,
      double baseRetryDelaySeconds,
      double maxRetryDelaySeconds) {
    return new AirtableClient(
        "appX",
        "key",
        "https://api.airtable.com/v0",
        new CacheStore(),
        maxRetries,
        baseRetryDelaySeconds,
        maxRetryDelaySeconds,
        30.0,
        transport);
  }

  /** Transport that answers 429 (with optional Retry-After) {@code failures} times, then 200. */
  private static FakeTransport flakyTransport(int failures, String retryAfter) {
    return new FakeTransport(
        (request, callIndex) -> {
          if (callIndex < failures) {
            Map<String, List<String>> headers =
                retryAfter != null ? Map.of("Retry-After", List.of(retryAfter)) : Map.of();
            return new FakeTransport.Canned(
                429,
                "{\"error\": {\"type\": \"RATE_LIMITED\", \"message\": \"slow down\"}}",
                headers);
          }
          return FakeTransport.Canned.ok(OK_BODY);
        });
  }

  private static long elapsedMillis(long startNanos) {
    return (System.nanoTime() - startNanos) / 1_000_000;
  }

  // ---- Closeable ownership ----

  @Test
  void closeDoesNotCloseInjectedClient() {
    FakeTransport injected = new FakeTransport((request, i) -> FakeTransport.Canned.ok(OK_BODY));
    AirtableClient client = client(injected, 3, 0.5, 30.0);
    client.listRecords("tbl1", new AirtableQuery());
    client.close();
    assertFalse(injected.isClosed(), "injected client must survive AirtableClient.close()");
    // The injected client is still fully usable after close().
    client.listRecords("tbl2", new AirtableQuery());
    assertEquals(2, injected.callCount());
    // The caller closes the injected client themselves — no exception.
    injected.close();
    assertTrue(injected.isClosed());
  }

  @Test
  void closeClosesOwnedEngine() {
    // No injected client: the AirtableClient owns a real JDK HttpClient. apiBase points
    // at a dead local port so a regression (engine left open) fails fast with a
    // connection error instead of hitting the real API — a *closed* engine fails before
    // any connection attempt, with IOException("closed").
    AirtableClient client =
        new AirtableClient(
            "appX", "key", "http://127.0.0.1:9", new CacheStore(), 3, 0.01, 0.05, 5.0, null);
    client.close();
    client.close(); // idempotent
    AirtableException.Network err =
        assertThrows(
            AirtableException.Network.class,
            () -> client.listRecords("tbl1", new AirtableQuery()),
            "request on a closed owned client must fail");
    assertEquals(
        "closed",
        err.getCause().getMessage(),
        "failure must come from the closed engine, not a live connection attempt");
  }

  // ---- Credential validation ----

  @Test
  void blankApiKeyThrowsMissingCredentials() {
    assertThrows(AirtableException.MissingCredentials.class, () -> new AirtableClient("appX", ""));
  }

  @Test
  void blankBaseIdThrowsMissingCredentials() {
    assertThrows(AirtableException.MissingCredentials.class, () -> new AirtableClient("  ", "key"));
  }

  // ---- Retry behavior ----

  @Test
  void rateLimitedThenSuccessRetriesWithJitteredBackoff() {
    FakeTransport transport = flakyTransport(1, null);
    AirtableClient client = client(transport, 3, 0.1, 30.0);
    long start = System.nanoTime();
    String payload = client.listRecords("tbl1", new AirtableQuery());
    long elapsed = elapsedMillis(start);
    assertEquals(OK_BODY, payload);
    assertEquals(2, transport.callCount());
    // No Retry-After header: backoff = 0.1s * 2^0, jittered into [50ms, 100ms).
    assertTrue(
        elapsed >= 50, "jittered backoff expected to wait at least 50ms, got " + elapsed + "ms");
    assertTrue(elapsed < 5000, "jittered backoff expected well under 5s, got " + elapsed + "ms");
  }

  @Test
  void numericRetryAfterIsHonoredExactly() {
    FakeTransport transport = flakyTransport(1, "0.05");
    // base 10s: if the Retry-After were ignored, the jittered backoff would wait >= 5s.
    AirtableClient client = client(transport, 3, 10.0, 30.0);
    long start = System.nanoTime();
    String payload = client.listRecords("tbl1", new AirtableQuery());
    long elapsed = elapsedMillis(start);
    assertEquals(OK_BODY, payload);
    // Server-provided value is honored exactly (no jitter): ~50ms, far below the 5s+ backoff.
    assertTrue(elapsed >= 50, "Retry-After: 0.05 must wait at least 50ms, got " + elapsed + "ms");
    assertTrue(
        elapsed < 5000,
        "Retry-After: 0.05 must preempt the jittered backoff, got " + elapsed + "ms");
  }

  @Test
  void absurdRetryAfterIsCappedAtMaxRetryDelay() {
    FakeTransport transport = flakyTransport(1, "3600");
    AirtableClient client = client(transport, 3, 0.01, 0.05);
    long start = System.nanoTime();
    String payload = client.listRecords("tbl1", new AirtableQuery());
    long elapsed = elapsedMillis(start);
    assertEquals(OK_BODY, payload);
    assertTrue(
        elapsed >= 50,
        "capped Retry-After must still wait maxRetryDelaySeconds (50ms), got " + elapsed + "ms");
    assertTrue(
        elapsed < 5000,
        "Retry-After: 3600 must be capped to maxRetryDelaySeconds (50ms), got " + elapsed + "ms");
  }

  @Test
  void httpDateRetryAfterInThePastWaitsZero() {
    FakeTransport transport = flakyTransport(1, "Wed, 21 Oct 2015 07:28:00 GMT");
    // base 10s: a regression to the jittered-backoff path would wait >= 5s.
    AirtableClient client = client(transport, 3, 10.0, 30.0);
    long start = System.nanoTime();
    String payload = client.listRecords("tbl1", new AirtableQuery());
    long elapsed = elapsedMillis(start);
    assertEquals(OK_BODY, payload);
    assertEquals(2, transport.callCount());
    assertTrue(
        elapsed < 5000, "HTTP-date in the past must floor the wait at 0, got " + elapsed + "ms");
  }

  @Test
  void terminal429ThrowsRateLimitedWithParsedRetryAfter() {
    FakeTransport transport = flakyTransport(10, "0.01");
    AirtableClient client = client(transport, 1, 0.01, 30.0);
    AirtableException.RateLimited err =
        assertThrows(
            AirtableException.RateLimited.class,
            () -> client.listRecords("tbl1", new AirtableQuery()));
    assertEquals(0.01, err.retryAfterSeconds());
  }

  // ---- Network exception wrapping ----

  @Test
  void transportIOExceptionSurfacesAsNetwork() {
    FakeTransport transport =
        new FakeTransport(
            (request, i) -> {
              throw new IOException("connection reset");
            });
    AirtableClient client = client(transport, 3, 0.01, 30.0);
    AirtableException.Network err =
        assertThrows(
            AirtableException.Network.class, () -> client.listRecords("tbl1", new AirtableQuery()));
    assertInstanceOf(IOException.class, err.getCause());
    assertTrue(err.getMessage().contains("connection reset"));
  }

  @Test
  void networkIsCaughtByTheAirtableExceptionContract() {
    FakeTransport transport =
        new FakeTransport(
            (request, i) -> {
              throw new IOException("boom");
            });
    AirtableClient client = client(transport, 3, 0.01, 30.0);
    try {
      client.listRecords("tbl1", new AirtableQuery());
      fail("expected a throw");
    } catch (AirtableException e) {
      assertInstanceOf(AirtableException.Network.class, e);
    }
  }

  @Test
  void networkEqualsSemanticsMatchSiblings() {
    assertEquals(
        new AirtableException.Network(new IOException("a")),
        new AirtableException.Network(new IOException("b")));
    assertNotEquals(
        new AirtableException.Network(new IOException("a")),
        new AirtableException.MissingCredentials());
  }
}
