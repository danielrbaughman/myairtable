package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.Authenticator;
import java.net.CookieHandler;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin myairtable-p7eb — list-cache policy: multi-page payloads carry a server-side
 * {@code offset} continuation token that expires, so they must never be cached; single-page
 * payloads are. The Kotlin suite injects a Ktor {@code MockEngine}; here the equivalent is a
 * minimal {@link HttpClient} subclass that returns canned 200 responses without touching the
 * network.
 */
class TestClientCachePolicy {

  /** A canned 200 JSON response; {@code request()} and {@code body()} come from the record. */
  private record CannedResponse<T>(HttpRequest request, T body) implements HttpResponse<T> {
    @Override
    public int statusCode() {
      return 200;
    }

    @Override
    public Optional<HttpResponse<T>> previousResponse() {
      return Optional.empty();
    }

    @Override
    public HttpHeaders headers() {
      return HttpHeaders.of(
          Map.of("Content-Type", List.of("application/json")), (name, value) -> true);
    }

    @Override
    public Optional<SSLSession> sslSession() {
      return Optional.empty();
    }

    @Override
    public URI uri() {
      return request.uri();
    }

    @Override
    public HttpClient.Version version() {
      return HttpClient.Version.HTTP_1_1;
    }
  }

  /** Fake transport: every send returns the configured body with status 200. */
  private static final class FakeHttpClient extends HttpClient {
    private final String responseBody;

    FakeHttpClient(String responseBody) {
      this.responseBody = responseBody;
    }

    @Override
    public <T> HttpResponse<T> send(HttpRequest request, HttpResponse.BodyHandler<T> handler) {
      // The AirtableClient always uses BodyHandlers.ofString(), so T is String.
      @SuppressWarnings("unchecked")
      T typedBody = (T) responseBody;
      return new CannedResponse<>(request, typedBody);
    }

    @Override
    public <T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request, HttpResponse.BodyHandler<T> handler) {
      return CompletableFuture.completedFuture(send(request, handler));
    }

    @Override
    public <T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> handler,
        HttpResponse.PushPromiseHandler<T> pushPromiseHandler) {
      return CompletableFuture.completedFuture(send(request, handler));
    }

    @Override
    public Optional<CookieHandler> cookieHandler() {
      return Optional.empty();
    }

    @Override
    public Optional<Duration> connectTimeout() {
      return Optional.empty();
    }

    @Override
    public Redirect followRedirects() {
      return Redirect.NEVER;
    }

    @Override
    public Optional<ProxySelector> proxy() {
      return Optional.empty();
    }

    @Override
    public SSLContext sslContext() {
      try {
        return SSLContext.getDefault();
      } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException(e);
      }
    }

    @Override
    public SSLParameters sslParameters() {
      return new SSLParameters();
    }

    @Override
    public Optional<Authenticator> authenticator() {
      return Optional.empty();
    }

    @Override
    public Version version() {
      return Version.HTTP_1_1;
    }

    @Override
    public Optional<Executor> executor() {
      return Optional.empty();
    }
  }

  private static AirtableClient clientReturning(String body) {
    return new AirtableClient(
        "appX",
        "key",
        "https://api.airtable.com/v0",
        new CacheStore(60.0),
        3,
        0.5,
        30.0,
        30.0,
        new FakeHttpClient(body));
  }

  @Test
  void singlePagePayloadIsCached() {
    AirtableClient client = clientReturning("{\"records\": []}");
    client.listRecords("tbl1", new AirtableQuery());
    assertEquals(1, client.getCache().count());
  }

  @Test
  void multiPagePayloadWithOffsetIsNotCached() {
    AirtableClient client = clientReturning("{\"records\": [], \"offset\": \"itrAbc/recDef\"}");
    client.listRecords("tbl1", new AirtableQuery());
    assertEquals(
        0, client.getCache().count(), "payloads with a live offset token must not be cached");
  }

  @Test
  void emptyStringOffsetCountsAsComplete() {
    AirtableClient client = clientReturning("{\"records\": [], \"offset\": \"\"}");
    client.listRecords("tbl1", new AirtableQuery());
    assertEquals(1, client.getCache().count());
  }

  @Test
  void getRecordCachingIsUnaffected() {
    AirtableClient client = clientReturning("{\"id\": \"recX\", \"fields\": {}}");
    client.getRecord("tbl1", "recX");
    assertEquals(1, client.getCache().count());
  }
}
