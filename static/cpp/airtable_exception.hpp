#pragma once

#include <exception>
#include <optional>
#include <stdexcept>
#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// Errors raised by the MyAirtable runtime (cpp-plan-v2 §2.3.7): catch
/// `AirtableException` for everything, or a specific subclass for targeted
/// handling. The 7-variant set matches the Swift/Kotlin/Java/C# targets.
class AirtableException : public std::runtime_error {
  protected:
    explicit AirtableException(const std::string& message) : std::runtime_error(message) {}
};

/// Non-2xx HTTP response. `body` is the raw response body if present.
class HttpError : public AirtableException {
  public:
    HttpError(int status_code, std::string body)
        : AirtableException(body.empty()
                                ? "AirtableException.HttpError(" + std::to_string(status_code) + ")"
                                : "AirtableException.HttpError(" + std::to_string(status_code) +
                                      "): " + body),
          status_code(status_code), body(std::move(body)) {}

    int status_code;
    std::string body;
};

/// Structured Airtable API error envelope (`{"error":{"type":...,"message":...}}`).
class ApiError : public AirtableException {
  public:
    ApiError(std::string code, std::string api_message)
        : AirtableException("AirtableException.ApiError(" + code + "): " + api_message),
          code(std::move(code)), api_message(std::move(api_message)) {}

    std::string code;
    std::string api_message;
};

/// JSON (de)serialization failure; carries the underlying parser message.
class DecodingError : public AirtableException {
  public:
    explicit DecodingError(const std::string& message)
        : AirtableException("AirtableException.DecodingError: " + message) {}
};

/// A request URL could not be constructed.
class InvalidUrlError : public AirtableException {
  public:
    explicit InvalidUrlError(const std::string& message)
        : AirtableException("AirtableException.InvalidUrlError: " + message) {}
};

/// Missing API key or base ID.
class MissingCredentialsError : public AirtableException {
  public:
    explicit MissingCredentialsError(const std::string& message)
        : AirtableException("AirtableException.MissingCredentialsError: " + message) {}
};

/// Transport-level failure that is NOT a 429 (DNS, connection reset, timeout, ...).
/// Carries the libcurl error description.
class NetworkError : public AirtableException {
  public:
    explicit NetworkError(const std::string& message)
        : AirtableException("AirtableException.NetworkError: " + message) {}
};

/// HTTP 429. `retry_after_seconds` is parsed from the Retry-After header when present.
class RateLimitedError : public AirtableException {
  public:
    explicit RateLimitedError(std::optional<double> retry_after_seconds)
        : AirtableException(retry_after_seconds.has_value()
                                ? "AirtableException.RateLimitedError(retryAfter=" +
                                      format_seconds(*retry_after_seconds) + "s)"
                                : "AirtableException.RateLimitedError"),
          retry_after_seconds(retry_after_seconds) {}

    std::optional<double> retry_after_seconds;

  private:
    static std::string format_seconds(double s) {
        // Render whole seconds without a trailing ".0" (parity with the C# message shape).
        if (s == static_cast<long long>(s)) {
            return std::to_string(static_cast<long long>(s));
        }
        auto text = std::to_string(s);
        while (!text.empty() && text.back() == '0') {
            text.pop_back();
        }
        if (!text.empty() && text.back() == '.') {
            text.pop_back();
        }
        return text;
    }
};

/// Convert a decoded non-2xx response body into the most specific exception.
///
/// Airtable's envelope is `{"error":{"type":"...","message":"..."}}`, or
/// `{"error":"STRING"}` on some legacy endpoints. Anything unparseable degrades
/// to `ApiError{"UNKNOWN", ...}` — never a secondary throw from the error path.
inline ApiError decode_error_envelope(const std::string& body) {
    json parsed = json::parse(body, /*cb=*/nullptr, /*allow_exceptions=*/false);
    if (parsed.is_discarded() || !parsed.is_object() || !parsed.contains("error")) {
        return ApiError("UNKNOWN", body);
    }
    const json& error = parsed.at("error");
    if (error.is_object()) {
        const std::string type = error.contains("type") && error.at("type").is_string()
                                     ? error.at("type").get<std::string>()
                                     : "UNKNOWN";
        const std::string message = error.contains("message") && error.at("message").is_string()
                                        ? error.at("message").get<std::string>()
                                        : "";
        return ApiError(type, message);
    }
    if (error.is_string()) {
        return ApiError("UNKNOWN", error.get<std::string>());
    }
    return ApiError("UNKNOWN", error.dump());
}

} // namespace myairtable
