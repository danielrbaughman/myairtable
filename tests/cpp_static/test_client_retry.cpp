// Retry policy: 429 always retried, 5xx/transport only when idempotent,
// backoff pure-function semantics (Java TestClientRetryPolicy + C# parity).
#include <catch2/catch_test_macros.hpp>

#include "airtable_client.hpp"
#include "fake_transport.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace {
AirtableClient fast_client(FakeTransport& transport) {
    // Zero base delay + zero jitter: retries execute instantly in tests.
    return AirtableClient("app1", "key1", transport.fn(), 0.0, 0.0);
}
} // namespace

// ---- compute_retry_delay_seconds (pure) ------------------------------------------

TEST_CASE("backoff grows exponentially with attempt", "[client][retry]") {
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 0, 0.0, 30.0, 0.0) ==
            0.5);
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 1, 0.0, 30.0, 0.0) ==
            1.0);
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 3, 0.0, 30.0, 0.0) ==
            4.0);
}

TEST_CASE("explicit retry-after wins over exponential backoff", "[client][retry]") {
    REQUIRE(AirtableClient::compute_retry_delay_seconds(7.0, 0.5, 3, 0.0, 30.0, 0.0) == 7.0);
}

TEST_CASE("jitter is bounded by min(delay, cap)", "[client][retry]") {
    // delay 4.0, cap 1.0, rand 1.0 → 4.0 + 1.0
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 3, 1.0, 30.0, 1.0) ==
            5.0);
    // delay 0.5 < cap → jitter bounded by the delay itself
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 0, 1.0, 30.0, 1.0) ==
            1.0);
}

TEST_CASE("max delay caps both backoff and a broken retry-after", "[client][retry]") {
    REQUIRE(AirtableClient::compute_retry_delay_seconds(std::nullopt, 0.5, 20, 1.0, 30.0, 1.0) ==
            30.0);
    REQUIRE(AirtableClient::compute_retry_delay_seconds(999999.0, 0.5, 0, 1.0, 30.0, 0.0) == 30.0);
}

TEST_CASE("negative retry-after is floored to zero", "[client][retry]") {
    REQUIRE(AirtableClient::compute_retry_delay_seconds(-5.0, 0.5, 0, 0.0, 30.0, 0.0) == 0.0);
}

// ---- parse_retry_after --------------------------------------------------------------

TEST_CASE("retry-after parses delta seconds", "[client][retry]") {
    HttpResponse response{429, "", {{"retry-after", "2.5"}}};
    REQUIRE(AirtableClient::parse_retry_after(response) == 2.5);
    REQUIRE(AirtableClient::parse_retry_after(HttpResponse{429, "", {}}) == std::nullopt);
}

// ---- live retry flow via FakeTransport ---------------------------------------------

TEST_CASE("429 is retried then succeeds", "[client][retry]") {
    FakeTransport transport;
    transport.respond(429, "{}").respond(429, "{}").respond(200, R"({"ok":true})");
    auto client = fast_client(transport);
    REQUIRE(client.send("GET", "https://x/y", std::nullopt, true) == R"({"ok":true})");
    REQUIRE(transport.calls() == 3);
}

TEST_CASE("429 is retried even for non-idempotent requests", "[client][retry]") {
    // A 429 means the server rejected the request — nothing was applied.
    FakeTransport transport;
    transport.respond(429, "{}").respond(200, R"({"created":1})");
    auto client = fast_client(transport);
    REQUIRE(client.send("POST", "https://x/y", "{}", false) == R"({"created":1})");
    REQUIRE(transport.calls() == 2);
}

TEST_CASE("429 exhausted throws RateLimitedError with retry-after", "[client][retry]") {
    FakeTransport transport;
    for (int i = 0; i < 5; ++i) {
        transport.respond(429, "{}", {{"retry-after", "0"}});
    }
    auto client = fast_client(transport);
    REQUIRE_THROWS_AS(client.send("GET", "https://x/y", std::nullopt, true), RateLimitedError);
    REQUIRE(transport.calls() == 5); // 1 + kMaxRetries
}

TEST_CASE("5xx is retried only when idempotent", "[client][retry]") {
    FakeTransport idempotent_transport;
    idempotent_transport.respond(503, "{}").respond(200, R"({"ok":1})");
    REQUIRE(fast_client(idempotent_transport).send("GET", "https://x/y", std::nullopt, true) ==
            R"({"ok":1})");
    REQUIRE(idempotent_transport.calls() == 2);

    FakeTransport non_idempotent_transport;
    non_idempotent_transport.respond(503, "boom");
    REQUIRE_THROWS_AS(
        fast_client(non_idempotent_transport).send("POST", "https://x/y", "{}", false), HttpError);
    REQUIRE(non_idempotent_transport.calls() == 1); // no double-insert risk taken
}

TEST_CASE("transport failure retried when idempotent, NetworkError when not", "[client][retry]") {
    FakeTransport recovering;
    recovering.fail("reset").respond(200, R"({"ok":1})");
    REQUIRE(fast_client(recovering).send("GET", "https://x/y", std::nullopt, true) ==
            R"({"ok":1})");

    FakeTransport failing;
    failing.fail("dns failure");
    try {
        fast_client(failing).send("POST", "https://x/y", "{}", false);
        FAIL("expected NetworkError");
    } catch (const NetworkError& e) {
        REQUIRE(std::string(e.what()).find("dns failure") != std::string::npos);
    }
    REQUIRE(failing.calls() == 1);
}
