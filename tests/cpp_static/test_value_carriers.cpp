// Value-carrier (de)serialization (C# TestValueCarriers parity).
#include <catch2/catch_test_macros.hpp>

#include "airtable_attachment.hpp"
#include "airtable_button.hpp"
#include "airtable_collaborator.hpp"
#include "airtable_record.hpp"
#include "sort.hpp"

using namespace myairtable;

TEST_CASE("attachment decodes full metadata incl nested thumbnails", "[carriers]") {
    auto a = json::parse(R"({
        "id": "att123", "url": "https://x/y.png", "filename": "y.png",
        "size": 1024, "type": "image/png",
        "thumbnails": {"small": {"url": "https://x/s.png", "width": 36, "height": 36},
                        "large": {"url": "https://x/l.png", "width": 512, "height": 512}}
    })")
                 .get<AirtableAttachment>();
    REQUIRE(a.id == "att123");
    REQUIRE(a.url == "https://x/y.png");
    REQUIRE(a.filename == "y.png");
    REQUIRE(a.size == 1024);
    REQUIRE(a.type == "image/png");
    REQUIRE(a.thumbnails->small->width == 36);
    REQUIRE(a.thumbnails->large->url == "https://x/l.png");
    REQUIRE(a.thumbnails->full == std::nullopt);
}

TEST_CASE("attachment upload shape is url-only, no null keys", "[carriers]") {
    auto upload = AirtableAttachment{.url = "https://example.com/file.pdf"};
    json encoded = upload;
    REQUIRE(encoded == json::parse(R"({"url":"https://example.com/file.pdf"})"));
}

TEST_CASE("collaborator decodes and id-only write shape round-trips", "[carriers]") {
    auto c =
        json::parse(R"({"id":"usr1","email":"a@b.co","name":"Ann","profilePicUrl":"https://p"})")
            .get<AirtableCollaborator>();
    REQUIRE(c.id == "usr1");
    REQUIRE(c.email == "a@b.co");
    REQUIRE(c.name == "Ann");
    REQUIRE(c.profile_pic_url == "https://p");

    json write_shape = AirtableCollaborator{.id = "usr1"};
    REQUIRE(write_shape == json::parse(R"({"id":"usr1"})"));
}

TEST_CASE("button decodes label and url", "[carriers]") {
    auto b = json::parse(R"({"label":"Open","url":"https://go"})").get<AirtableButton>();
    REQUIRE(b.label == "Open");
    REQUIRE(b.url == "https://go");
    // Airtable omits url when the button formula yields none.
    auto no_url = json::parse(R"({"label":"Open"})").get<AirtableButton>();
    REQUIRE(no_url.url == std::nullopt);
}

TEST_CASE("record envelope decodes id, createdTime, raw fields", "[carriers]") {
    auto r = json::parse(R"({
        "id": "recABC", "createdTime": "2024-01-15T10:30:00.000Z",
        "fields": {"fldX": "hello", "fldY": 5}
    })")
                 .get<AirtableRecord>();
    REQUIRE(r.id == "recABC");
    REQUIRE(r.created_time.epoch_millis() == 1'705'314'600'000);
    REQUIRE(r.fields.at("fldX") == "hello");
    // Fields default to an empty object when the record carries none.
    REQUIRE(json::parse(R"({"id":"recE"})").get<AirtableRecord>().fields == json::object());
}

TEST_CASE("sort direction wire values", "[carriers]") {
    REQUIRE(wire(SortDirection::Asc) == "asc");
    REQUIRE(wire(SortDirection::Desc) == "desc");
    Sort s{.field = "Name"};
    REQUIRE(s.direction == SortDirection::Asc); // default ascending
}
