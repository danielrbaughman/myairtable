// Airtable's create endpoint is a strict whitelist for attachments: only {url} /
// {url, filename}. Verified against the live API -- an id, alone or echoed alongside url,
// fails with INVALID_ATTACHMENT_OBJECT.

#include <catch2/catch_test_macros.hpp>

#include "airtable_json.hpp"

using myairtable::json;
using myairtable::project_attachments_for_create;

namespace {
json server_attachment_cell() {
    return json::array({json{{"id", "attServerSide0001"},
                             {"url", "https://example.com/a.png"},
                             {"filename", "a.png"},
                             {"size", 1234},
                             {"type", "image/png"},
                             {"width", 10},
                             {"height", 10},
                             {"thumbnails", json{{"small", json{{"url", "x"}}}}}}});
}
} // namespace

TEST_CASE("duplicate payload: strips read-only attachment metadata", "[json][duplicate]") {
    const json fields = json{{"fldAtt", server_attachment_cell()}};
    const json projected = project_attachments_for_create(fields);

    REQUIRE(projected.at("fldAtt").size() == 1);
    const json& only = projected.at("fldAtt").at(0);
    REQUIRE(only.at("url") == "https://example.com/a.png");
    REQUIRE(only.at("filename") == "a.png");
    // id is what create rejects; the rest are read-only echoes.
    REQUIRE_FALSE(only.contains("id"));
    REQUIRE_FALSE(only.contains("size"));
    REQUIRE_FALSE(only.contains("type"));
    REQUIRE_FALSE(only.contains("thumbnails"));
}

TEST_CASE("duplicate payload: passes through caller-built attachments", "[json][duplicate]") {
    const json fields = json{{"fldAtt", json::array({json{{"url", "u"}}})}};
    REQUIRE(project_attachments_for_create(fields) == fields);
}

TEST_CASE("duplicate payload: leaves other cell types alone", "[json][duplicate]") {
    // Linked records, collaborators and plain arrays must not be mistaken for attachments.
    const json fields = json{
        {"fldLink", json::array({"rec1", "rec2"})},
        {"fldUser", json{{"id", "usrX"}, {"email", "e@x.com"}}},
        {"fldUsers", json::array({json{{"id", "usrX"}, {"email", "e@x.com"}}})},
        {"fldEmpty", json::array()},
        {"fldText", "https://example.com"},
    };
    REQUIRE(project_attachments_for_create(fields) == fields);
}

TEST_CASE("duplicate payload: does not mutate the caller's json", "[json][duplicate]") {
    const json fields = json{{"fldAtt", server_attachment_cell()}};
    const json before = fields;
    (void)project_attachments_for_create(fields);
    REQUIRE(fields == before);
}
