// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.Objects;

/**
 * Errors raised by the MyAirtable runtime.
 *
 * <p>A sealed, UNCHECKED exception hierarchy (java-plan-v2 §2.3.7): catch {@link AirtableException}
 * for everything, or a specific subclass — or pattern-match with {@code switch} — for targeted
 * handling. Unchecked because checked exceptions would poison every generated signature.
 */
public abstract sealed class AirtableException extends RuntimeException
    permits AirtableException.Http,
        AirtableException.Api,
        AirtableException.Decoding,
        AirtableException.InvalidUrl,
        AirtableException.MissingCredentials,
        AirtableException.Network,
        AirtableException.RateLimited {

  private AirtableException(String message, Throwable cause) {
    super(message, cause);
  }

  /** Non-2xx HTTP response. {@code body} is the raw response body if decodable as UTF-8. */
  public static final class Http extends AirtableException {
    private final int statusCode;
    private final String body;

    public Http(int statusCode, String body) {
      super(
          body == null || body.isEmpty()
              ? "AirtableException.Http(" + statusCode + ")"
              : "AirtableException.Http(" + statusCode + "): " + body,
          null);
      this.statusCode = statusCode;
      this.body = body;
    }

    public int statusCode() {
      return statusCode;
    }

    public String body() {
      return body;
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof Http h && h.statusCode == statusCode && Objects.equals(h.body, body);
    }

    @Override
    public int hashCode() {
      return 31 * statusCode + Objects.hashCode(body);
    }
  }

  /**
   * Airtable returned a structured error envelope ({@code {"error": {"type": ..., "message":
   * ...}}}).
   */
  public static final class Api extends AirtableException {
    private final String code;
    private final String apiMessage;

    public Api(String code, String apiMessage) {
      super("AirtableException.Api(" + code + "): " + apiMessage, null);
      this.code = code;
      this.apiMessage = apiMessage;
    }

    public String code() {
      return code;
    }

    public String apiMessage() {
      return apiMessage;
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof Api a && a.code.equals(code) && a.apiMessage.equals(apiMessage);
    }

    @Override
    public int hashCode() {
      return 31 * code.hashCode() + apiMessage.hashCode();
    }
  }

  /** JSON decoding failed. {@code cause} originates from Jackson. */
  public static final class Decoding extends AirtableException {
    public Decoding(Throwable cause) {
      super("AirtableException.Decoding: " + (cause == null ? null : cause.getMessage()), cause);
    }

    // Underlying decode errors are not comparable; treat all decoding errors as equal.
    @Override
    public boolean equals(Object other) {
      return other instanceof Decoding;
    }

    @Override
    public int hashCode() {
      return getClass().hashCode();
    }
  }

  /** A request URL could not be constructed. */
  public static final class InvalidUrl extends AirtableException {
    public InvalidUrl() {
      super("AirtableException.InvalidUrl", null);
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof InvalidUrl;
    }

    @Override
    public int hashCode() {
      return getClass().hashCode();
    }
  }

  /** {@link AirtableClient} was initialized without an API key or base ID. */
  public static final class MissingCredentials extends AirtableException {
    public MissingCredentials() {
      super("AirtableException.MissingCredentials", null);
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof MissingCredentials;
    }

    @Override
    public int hashCode() {
      return getClass().hashCode();
    }
  }

  /**
   * A transport-level failure (connect, DNS, socket, request timeout) — the request never produced
   * an HTTP response. {@code cause} is the underlying I/O exception. Thread interruption is
   * re-asserted before wrapping.
   */
  public static final class Network extends AirtableException {
    public Network(Throwable cause) {
      super("AirtableException.Network: " + (cause == null ? null : cause.getMessage()), cause);
    }

    // Underlying transport errors are not comparable; treat all network errors as equal.
    @Override
    public boolean equals(Object other) {
      return other instanceof Network;
    }

    @Override
    public int hashCode() {
      return getClass().hashCode();
    }
  }

  /**
   * Airtable returned 429 Too Many Requests. {@code retryAfterSeconds} is the {@code Retry-After}
   * header value in seconds if present (else {@code null}).
   */
  public static final class RateLimited extends AirtableException {
    private final Double retryAfterSeconds;

    public RateLimited(Double retryAfterSeconds) {
      super(
          retryAfterSeconds != null
              ? "AirtableException.RateLimited(retryAfter: " + retryAfterSeconds + "s)"
              : "AirtableException.RateLimited",
          null);
      this.retryAfterSeconds = retryAfterSeconds;
    }

    public Double retryAfterSeconds() {
      return retryAfterSeconds;
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof RateLimited r
          && Objects.equals(r.retryAfterSeconds, retryAfterSeconds);
    }

    @Override
    public int hashCode() {
      return Objects.hashCode(retryAfterSeconds);
    }
  }
}
