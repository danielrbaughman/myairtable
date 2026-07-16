// URL encoding (Java TestClientUrlEncoding parity + the '+' hazard pins).
#include <catch2/catch_test_macros.hpp>

#include "airtable_client.hpp"
#include "fake_transport.hpp"

using namespace myairtable;

TEST_CASE("plus encodes as %2B, never a raw plus", "[client][url]") {
    // Airtable decodes a raw '+' as a space, corrupting formulas like LEN({f})+1
    // (the Swift/Ktor live-caught bug — C++ must land on the %2B side).
    REQUIRE(url_encode("LEN({Notes})+1") == "LEN%28%7BNotes%7D%29%2B1");
    REQUIRE(url_encode("+") == "%2B");
}

TEST_CASE("space encodes as %20, unreserved pass through", "[client][url]") {
    REQUIRE(url_encode("a b") == "a%20b");
    REQUIRE(url_encode("AZaz09-_.~") == "AZaz09-_.~");
    REQUIRE(url_encode("{Name} = 'x'") == "%7BName%7D%20%3D%20%27x%27");
}

TEST_CASE("utf-8 bytes percent-encode", "[client][url]") {
    REQUIRE(url_encode("é") == "%C3%A9");
}

TEST_CASE("table_url encodes values but keeps param-name brackets raw", "[client][url]") {
    myairtable_tests::FakeTransport transport;
    AirtableClient client("app123", "key", transport.fn(), 0.0, 0.0);
    const auto url =
        client.table_url("tblX", {{"filterByFormula", "LEN({f})+1"}, {"fields[]", "fldA"}});
    REQUIRE(url == "https://api.airtable.com/v0/app123/tblX?filterByFormula=LEN%28%7Bf%7D%29%2B1"
                   "&fields[]=fldA");
}

TEST_CASE("path segments are encoded", "[client][url]") {
    myairtable_tests::FakeTransport transport;
    AirtableClient client("app 1", "key", transport.fn(), 0.0, 0.0);
    REQUIRE(client.table_url("Table Name", {}) ==
            "https://api.airtable.com/v0/app%201/Table%20Name");
}
