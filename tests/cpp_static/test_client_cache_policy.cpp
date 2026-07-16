// Client read-cache policy (Java TestClientCachePolicy parity + the C# offset-page skip).
#include <catch2/catch_test_macros.hpp>

#include "airtable_client.hpp"
#include "fake_transport.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace {
AirtableClient cached_client(FakeTransport& transport, double cache_seconds = 60.0) {
    return AirtableClient("app1", "key1", transport.fn(), 0.0, 0.0, cache_seconds);
}
} // namespace

TEST_CASE("get_record is served from cache on the second call", "[client][cache]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1"})");
    auto client = cached_client(transport);
    REQUIRE(client.get_record("tbl1", "rec1") == R"({"id":"rec1"})");
    REQUIRE(client.get_record("tbl1", "rec1") == R"({"id":"rec1"})");
    REQUIRE(transport.calls() == 1);
}

TEST_CASE("caching is off by default", "[client][cache]") {
    FakeTransport transport;
    transport.respond(200, "{}").respond(200, "{}");
    auto client = cached_client(transport, 0.0);
    client.get_record("tbl1", "rec1");
    client.get_record("tbl1", "rec1");
    REQUIRE(transport.calls() == 2);
}

TEST_CASE("list cache keys distinguish structurally different queries", "[client][cache]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[]})").respond(200, R"({"records":[]})");
    auto client = cached_client(transport);
    client.list_records("tbl1", AirtableQuery{.max_records = 1});
    client.list_records("tbl1", AirtableQuery{.max_records = 2});
    REQUIRE(transport.calls() == 2);
    client.list_records("tbl1", AirtableQuery{.max_records = 1}); // hit
    REQUIRE(transport.calls() == 2);
}

TEST_CASE("mutations invalidate the table's cached reads", "[client][cache]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","v":1})")
        .respond(200, R"({"records":[]})") // the create
        .respond(200, R"({"id":"rec1","v":2})");
    auto client = cached_client(transport);
    client.get_record("tbl1", "rec1");
    client.create_records("tbl1", R"({"records":[]})");
    REQUIRE(client.get_record("tbl1", "rec1") == R"({"id":"rec1","v":2})");
    REQUIRE(transport.calls() == 3);
}

TEST_CASE("a list page with a live offset token is never cached", "[client][cache]") {
    // The C# late-caught bug: caching a page whose offset token has expired
    // server-side would replay a dead token on the follow-up fetch.
    FakeTransport transport;
    transport.respond(200, R"({"records":[],"offset":"itrToken"})")
        .respond(200, R"({"records":[],"offset":"itrToken2"})");
    auto client = cached_client(transport);
    client.list_records("tbl1", AirtableQuery{});
    client.list_records("tbl1", AirtableQuery{});
    REQUIRE(transport.calls() == 2); // no cache hit
}

TEST_CASE("invalidate_all_caches clears every table", "[client][cache]") {
    FakeTransport transport;
    transport.respond(200, "{}").respond(200, "{}").respond(200, "{}").respond(200, "{}");
    auto client = cached_client(transport);
    client.get_record("tblA", "r1");
    client.get_record("tblB", "r2");
    client.invalidate_all_caches();
    client.get_record("tblA", "r1");
    client.get_record("tblB", "r2");
    REQUIRE(transport.calls() == 4);
}
