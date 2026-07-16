using System;

namespace MyAirtable;

/// <summary>
/// Errors raised by the MyAirtable runtime. An UNCHECKED exception hierarchy
/// (csharp-plan-v2 §2.3.7): catch <see cref="AirtableException"/> for everything, or
/// pattern-match a specific nested subclass for targeted handling. The 7-variant set
/// matches the Swift/Kotlin/Java targets.
/// </summary>
public abstract class AirtableException : Exception
{
    private protected AirtableException(string message, Exception? inner = null)
        : base(message, inner) { }

    /// <summary>Non-2xx HTTP response. <see cref="Body"/> is the raw response body if present.</summary>
    public sealed class HttpError : AirtableException
    {
        public int StatusCode { get; }
        public string? Body { get; }

        public HttpError(int statusCode, string? body)
            : base(
                string.IsNullOrEmpty(body)
                    ? $"AirtableException.HttpError({statusCode})"
                    : $"AirtableException.HttpError({statusCode}): {body}"
            )
        {
            StatusCode = statusCode;
            Body = body;
        }
    }

    /// <summary>Structured Airtable API error envelope (<c>{"error":{"type":...,"message":...}}</c>).</summary>
    public sealed class ApiError : AirtableException
    {
        public string Code { get; }
        public string ApiMessage { get; }

        public ApiError(string code, string apiMessage)
            : base($"AirtableException.ApiError({code}): {apiMessage}")
        {
            Code = code;
            ApiMessage = apiMessage;
        }
    }

    /// <summary>JSON (de)serialization failure; wraps the underlying exception.</summary>
    public sealed class DecodingError : AirtableException
    {
        public DecodingError(string message, Exception? inner = null)
            : base($"AirtableException.DecodingError: {message}", inner) { }
    }

    /// <summary>A request URL could not be constructed.</summary>
    public sealed class InvalidUrlError : AirtableException
    {
        public InvalidUrlError(string message)
            : base($"AirtableException.InvalidUrlError: {message}") { }
    }

    /// <summary>Missing API key or base ID.</summary>
    public sealed class MissingCredentialsError : AirtableException
    {
        public MissingCredentialsError(string message)
            : base($"AirtableException.MissingCredentialsError: {message}") { }
    }

    /// <summary>
    /// Transport-level failure that is NOT a 429 (DNS, connection reset, timeout, ...).
    /// Wraps the underlying <see cref="HttpRequestException"/> or <see cref="TaskCanceledException"/>.
    /// </summary>
    public sealed class NetworkError : AirtableException
    {
        public NetworkError(string message, Exception? inner = null)
            : base($"AirtableException.NetworkError: {message}", inner) { }
    }

    /// <summary>HTTP 429. <see cref="RetryAfterSeconds"/> is parsed from the Retry-After header when present.</summary>
    public sealed class RateLimitedError : AirtableException
    {
        public double? RetryAfterSeconds { get; }

        public RateLimitedError(double? retryAfterSeconds)
            : base(
                retryAfterSeconds is { } s
                    ? $"AirtableException.RateLimitedError(retryAfter={s}s)"
                    : "AirtableException.RateLimitedError"
            )
        {
            RetryAfterSeconds = retryAfterSeconds;
        }
    }
}
