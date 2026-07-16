// Client hardening: credentials, auth headers, endpoint URLs/methods, error
// mapping (Java TestClientHardening parity, ~15 cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_client.hpp"
#include "fake_transport.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace {
AirtableClient fast_client(FakeTransport& transport) {
    return AirtableClient("app1", "key1", transport.fn(), 0.0, 0.0);
}
} // namespace

TEST_CASE("empty credentials throw MissingCredentialsError", "[client]") {
    FakeTransport transport;
    REQUIRE_THROWS_AS(AirtableClient("", "key", transport.fn(), 0.0, 0.0), MissingCredentialsError);
    REQUIRE_THROWS_AS(AirtableClient("app", "", transport.fn(), 0.0, 0.0), MissingCredentialsError);
}

TEST_CASE("bearer auth header is attached to every request", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).get_record("tbl1", "rec1");
    const auto& request = transport.requests().front();
    bool found = false;
    for (const auto& [key, value] : request.headers) {
        if (key == "Authorization" && value == "Bearer key1") {
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("json content-type accompanies bodies and only bodies", "[client]") {
    FakeTransport transport;
    transport.respond(200).respond(200);
    auto client = fast_client(transport);
    client.create_records("tbl1", R"({"records":[]})");
    client.get_record("tbl1", "rec1");
    const auto has_content_type = [](const HttpRequest& request) {
        for (const auto& [key, value] : request.headers) {
            if (key == "Content-Type") {
                return true;
            }
        }
        return false;
    };
    REQUIRE(has_content_type(transport.requests()[0]));
    REQUIRE_FALSE(has_content_type(transport.requests()[1]));
}

TEST_CASE("get_record hits the single-record URL with returnFieldsByFieldId", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).get_record("tbl1", "rec1");
    REQUIRE(transport.requests().front().url ==
            "https://api.airtable.com/v0/app1/tbl1/rec1?returnFieldsByFieldId=true");
    REQUIRE(transport.requests().front().method == "GET");
}

TEST_CASE("create posts to the table collection", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).create_records("tbl1", R"({"records":[]})");
    REQUIRE(transport.requests().front().method == "POST");
    REQUIRE(transport.requests().front().url == "https://api.airtable.com/v0/app1/tbl1");
    REQUIRE(transport.requests().front().body == R"({"records":[]})");
}

TEST_CASE("update patches the table collection", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).update_records("tbl1", R"({"records":[]})");
    REQUIRE(transport.requests().front().method == "PATCH");
}

TEST_CASE("delete_record targets the record URL", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).delete_record("tbl1", "rec9");
    REQUIRE(transport.requests().front().method == "DELETE");
    REQUIRE(transport.requests().front().url == "https://api.airtable.com/v0/app1/tbl1/rec9");
}

TEST_CASE("delete_records builds repeated records[] params", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).delete_records("tbl1", {"rec1", "rec2"});
    REQUIRE(transport.requests().front().url ==
            "https://api.airtable.com/v0/app1/tbl1?records[]=rec1&records[]=rec2");
}

TEST_CASE("list_records flattens the query onto the URL", "[client]") {
    FakeTransport transport;
    transport.respond(200);
    fast_client(transport).list_records("tbl1", AirtableQuery{.max_records = 3});
    REQUIRE(transport.requests().front().url ==
            "https://api.airtable.com/v0/app1/tbl1?maxRecords=3&returnFieldsByFieldId=true");
}

TEST_CASE("structured 4xx maps to ApiError with type and message", "[client]") {
    FakeTransport transport;
    transport.respond(404, R"({"error":{"type":"NOT_FOUND","message":"Record not found"}})");
    try {
        fast_client(transport).get_record("tbl1", "recMissing");
        FAIL("expected ApiError");
    } catch (const ApiError& e) {
        REQUIRE(e.code == "NOT_FOUND");
        REQUIRE(e.api_message == "Record not found");
    }
}

TEST_CASE("legacy string envelope maps to ApiError", "[client]") {
    FakeTransport transport;
    transport.respond(404, R"({"error":"NOT_FOUND"})");
    REQUIRE_THROWS_AS(fast_client(transport).get_record("tbl1", "recX"), ApiError);
}

TEST_CASE("non-envelope 4xx maps to HttpError with status and body", "[client]") {
    FakeTransport transport;
    transport.respond(418, "just text");
    try {
        fast_client(transport).get_record("tbl1", "recX");
        FAIL("expected HttpError");
    } catch (const HttpError& e) {
        REQUIRE(e.status_code == 418);
        REQUIRE(e.body == "just text");
    }
}

TEST_CASE("2xx passes the payload through untouched", "[client]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[{"id":"rec1"}]})");
    REQUIRE(fast_client(transport).list_records("tbl1", AirtableQuery{}) ==
            R"({"records":[{"id":"rec1"}]})");
}

TEST_CASE("base_id accessor reflects construction", "[client]") {
    FakeTransport transport;
    REQUIRE(fast_client(transport).base_id() == "app1");
}
