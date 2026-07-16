// Error-envelope decoding + exception hierarchy (Java TestAirtableExceptionDecoding parity).
#include <catch2/catch_test_macros.hpp>

#include "airtable_exception.hpp"

using namespace myairtable;

TEST_CASE("all seven variants are AirtableExceptions", "[exceptions]") {
    // Compile-time: every subclass converts to the base; runtime: catchable as base.
    const auto throws_as_base = [](auto&& make) {
        try {
            throw make();
        } catch (const AirtableException&) {
            return true;
        } catch (...) {
            return false;
        }
    };
    REQUIRE(throws_as_base([] { return HttpError(500, "boom"); }));
    REQUIRE(throws_as_base([] { return ApiError("TYPE", "msg"); }));
    REQUIRE(throws_as_base([] { return DecodingError("bad json"); }));
    REQUIRE(throws_as_base([] { return InvalidUrlError("bad url"); }));
    REQUIRE(throws_as_base([] { return MissingCredentialsError("no key"); }));
    REQUIRE(throws_as_base([] { return NetworkError("connection reset"); }));
    REQUIRE(throws_as_base([] { return RateLimitedError(1.5); }));
}

TEST_CASE("structured error decodes to ApiError with type and message", "[exceptions]") {
    auto e =
        decode_error_envelope(R"({"error":{"type":"INVALID_REQUEST_UNKNOWN","message":"Nope"}})");
    REQUIRE(e.code == "INVALID_REQUEST_UNKNOWN");
    REQUIRE(e.api_message == "Nope");
}

TEST_CASE("structured error with missing message decodes to empty string", "[exceptions]") {
    auto e = decode_error_envelope(R"({"error":{"type":"SOMETYPE"}})");
    REQUIRE(e.code == "SOMETYPE");
    REQUIRE(e.api_message.empty());
}

TEST_CASE("legacy string-form error decodes to ApiError with code UNKNOWN", "[exceptions]") {
    auto e = decode_error_envelope(R"({"error":"NOT_FOUND"})");
    REQUIRE(e.code == "UNKNOWN");
    REQUIRE(e.api_message == "NOT_FOUND");
}

TEST_CASE("common Airtable error types decode cleanly", "[exceptions]") {
    for (const auto* type :
         {"AUTHENTICATION_REQUIRED", "NOT_FOUND", "INVALID_PERMISSIONS", "ROW_DOES_NOT_EXIST",
          "INVALID_VALUE_FOR_COLUMN", "UNKNOWN_FIELD_NAME", "INVALID_MULTIPLE_CHOICE_OPTIONS"}) {
        auto body = std::string(R"({"error":{"type":")") + type + R"(","message":"m"}})";
        auto e = decode_error_envelope(body);
        REQUIRE(e.code == type);
        REQUIRE(e.api_message == "m");
    }
}

TEST_CASE("malformed body degrades to UNKNOWN ApiError, never throws", "[exceptions]") {
    REQUIRE(decode_error_envelope("not json at all").code == "UNKNOWN");
    REQUIRE(decode_error_envelope("").code == "UNKNOWN");
    REQUIRE(decode_error_envelope(R"({"noError": true})").code == "UNKNOWN");
    REQUIRE(decode_error_envelope(R"({"error": 42})").code == "UNKNOWN");
    REQUIRE(decode_error_envelope(R"({"error": 42})").api_message == "42");
}

TEST_CASE("exception message is human readable", "[exceptions]") {
    REQUIRE(std::string(ApiError("NOT_FOUND", "Record rec123 missing").what()) ==
            "AirtableException.ApiError(NOT_FOUND): Record rec123 missing");
    REQUIRE(std::string(DecodingError("truncated").what()) ==
            "AirtableException.DecodingError: truncated");
}

TEST_CASE("rate limited with retry-after formats correctly", "[exceptions]") {
    REQUIRE(std::string(RateLimitedError(30.0).what()) ==
            "AirtableException.RateLimitedError(retryAfter=30s)");
    REQUIRE(std::string(RateLimitedError(std::nullopt).what()) ==
            "AirtableException.RateLimitedError");
    REQUIRE(RateLimitedError(1.5).retry_after_seconds == 1.5);
}

TEST_CASE("http without body omits body text", "[exceptions]") {
    REQUIRE(std::string(HttpError(500, "").what()) == "AirtableException.HttpError(500)");
    auto with_body = HttpError(422, R"({"error":"x"})");
    REQUIRE(with_body.status_code == 422);
    REQUIRE(std::string(with_body.what()) == R"(AirtableException.HttpError(422): {"error":"x"})");
}

TEST_CASE("catching a specific subclass works alongside the base", "[exceptions]") {
    bool caught_specific = false;
    try {
        throw RateLimitedError(2.0);
    } catch (const HttpError&) {
        FAIL("wrong subclass");
    } catch (const RateLimitedError& e) {
        caught_specific = e.retry_after_seconds == 2.0;
    }
    REQUIRE(caught_specific);
}
