package myairtable;

import java.io.IOException;
import java.net.Authenticator;
import java.net.CookieHandler;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.Flow;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;

/**
 * Programmable fake {@link HttpClient} for offline client tests — the Java analog of Ktor's {@code
 * MockEngine} used by the Kotlin twins (TestClientHardening.kt, TestTableBoundedOps.kt). Extends
 * the {@code FakeHttpClient} pattern from {@link TestClientCachePolicy} with per-call sequenced
 * responses (retry tests), arbitrary status codes and headers, simulated transport failures
 * (responders may throw {@link IOException}), a request log, and close() tracking.
 *
 * <p>Thread-safe: the request log is synchronized and the call counter atomic, so the bounded
 * multi-get fan-out (virtual threads) can record concurrently.
 */
final class FakeTransport extends HttpClient {

  /** A canned response: status + body + headers. */
  record Canned(int status, String body, Map<String, List<String>> headers) {
    static final Map<String, List<String>> JSON_HEADERS =
        Map.of("Content-Type", List.of("application/json"));

    static Canned ok(String body) {
      return new Canned(200, body, JSON_HEADERS);
    }
  }

  /** Computes the response for a call; may throw {@link IOException} to simulate transport loss. */
  @FunctionalInterface
  interface Responder {
    Canned respond(HttpRequest request, int callIndex) throws IOException;
  }

  private final Responder responder;
  private final List<HttpRequest> requests = Collections.synchronizedList(new ArrayList<>());
  private final AtomicInteger calls = new AtomicInteger();
  private volatile boolean closed = false;

  FakeTransport(Responder responder) {
    this.responder = responder;
  }

  /** Every request seen, in arrival order (mirrors MockEngine's {@code requestHistory}). */
  List<HttpRequest> requestHistory() {
    return List.copyOf(requests);
  }

  int callCount() {
    return calls.get();
  }

  boolean isClosed() {
    return closed;
  }

  /** Drains a request's {@code BodyPublisher} into UTF-8 text, for PATCH-body assertions. */
  static String bodyText(HttpRequest request) {
    return request
        .bodyPublisher()
        .map(
            publisher -> {
              HttpResponse.BodySubscriber<String> subscriber =
                  HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
              publisher.subscribe(
                  new Flow.Subscriber<ByteBuffer>() {
                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                      subscriber.onSubscribe(subscription);
                    }

                    @Override
                    public void onNext(ByteBuffer item) {
                      subscriber.onNext(List.of(item));
                    }

                    @Override
                    public void onError(Throwable throwable) {
                      subscriber.onError(throwable);
                    }

                    @Override
                    public void onComplete() {
                      subscriber.onComplete();
                    }
                  });
              return subscriber.getBody().toCompletableFuture().join();
            })
        .orElse("");
  }

  @Override
  public <T> HttpResponse<T> send(HttpRequest request, HttpResponse.BodyHandler<T> handler)
      throws IOException {
    int index = calls.getAndIncrement();
    requests.add(request);
    Canned canned = responder.respond(request, index);
    // The AirtableClient always uses BodyHandlers.ofString(), so T is String.
    @SuppressWarnings("unchecked")
    T typedBody = (T) canned.body();
    return new Response<>(
        request,
        canned.status(),
        typedBody,
        HttpHeaders.of(canned.headers(), (name, value) -> true));
  }

  @Override
  public <T> CompletableFuture<HttpResponse<T>> sendAsync(
      HttpRequest request, HttpResponse.BodyHandler<T> handler) {
    try {
      return CompletableFuture.completedFuture(send(request, handler));
    } catch (IOException e) {
      return CompletableFuture.failedFuture(e);
    }
  }

  @Override
  public <T> CompletableFuture<HttpResponse<T>> sendAsync(
      HttpRequest request,
      HttpResponse.BodyHandler<T> handler,
      HttpResponse.PushPromiseHandler<T> pushPromiseHandler) {
    return sendAsync(request, handler);
  }

  @Override
  public void close() {
    closed = true;
  }

  /** A canned {@link HttpResponse} carrying the configured status/body/headers. */
  private record Response<T>(HttpRequest request, int status, T bodyValue, HttpHeaders headerValues)
      implements HttpResponse<T> {
    @Override
    public int statusCode() {
      return status;
    }

    @Override
    public T body() {
      return bodyValue;
    }

    @Override
    public HttpHeaders headers() {
      return headerValues;
    }

    @Override
    public Optional<HttpResponse<T>> previousResponse() {
      return Optional.empty();
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

  // ---- inert HttpClient plumbing ----

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
