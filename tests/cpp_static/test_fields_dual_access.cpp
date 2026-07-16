// Fields dual ID/name access (Java TestFieldsDualAccess parity, 14 cases).
#include <catch2/catch_test_macros.hpp>

#include "fields.hpp"

using namespace myairtable;

namespace {
Fields make_fields() {
    return Fields({{"fld001", json("hello")}, {"fld002", json(42.0)}},
                  {{"Primary Key", "fld001"}, {"Count", "fld002"}});
}
} // namespace

TEST_CASE("id lookup returns the stored value", "[fields]") {
    REQUIRE(make_fields().get("fld001") == json("hello"));
}

TEST_CASE("name lookup translates to id and returns the same value", "[fields]") {
    auto fields = make_fields();
    REQUIRE(fields.get("Primary Key") == json("hello"));
    REQUIRE(fields.get("Primary Key") == fields.get("fld001"));
}

TEST_CASE("id is tried first when a name and an unrelated id collide", "[fields]") {
    // A storage key that HAPPENS to equal a mapped name: direct hit wins.
    Fields fields({{"Primary Key", json("stored-under-raw-key")}, {"fld001", json("by-id")}},
                  {{"Primary Key", "fld001"}});
    REQUIRE(fields.get("Primary Key") == json("stored-under-raw-key"));
}

TEST_CASE("set is id-first when a name and an unrelated id collide", "[fields]") {
    Fields fields({{"Primary Key", json("raw")}, {"fld001", json("by-id")}},
                  {{"Primary Key", "fld001"}});
    fields.set("Primary Key", json("updated"));
    REQUIRE(fields.get("Primary Key") == json("updated"));
    REQUIRE(fields.get("fld001") == json("by-id")); // untouched
}

TEST_CASE("set treats known id as id even when absent from storage", "[fields]") {
    Fields fields({}, {{"Primary Key", "fld001"}});
    fields.set("fld001", json("x"));
    REQUIRE(fields.get("Primary Key") == json("x"));
}

TEST_CASE("set by name stores under the translated id, not the name itself", "[fields]") {
    Fields fields({}, {{"Primary Key", "fld001"}});
    fields.set("Primary Key", json("x"));
    REQUIRE(fields.to_map().contains("fld001"));
    REQUIRE_FALSE(fields.to_map().contains("Primary Key"));
}

TEST_CASE("unknown name without mapping stores under the raw key", "[fields]") {
    Fields fields;
    fields.set("Mystery", json(1));
    REQUIRE(fields.to_map().contains("Mystery"));
}

TEST_CASE("remove drops the entry entirely", "[fields]") {
    auto fields = make_fields();
    fields.remove("Primary Key"); // via name
    REQUIRE_FALSE(fields.has("fld001"));
    REQUIRE(fields.count() == 1);
}

TEST_CASE("json null is stored as JSON null to clear the field server-side", "[fields]") {
    auto fields = make_fields();
    fields.set("Primary Key", json(nullptr));
    REQUIRE(fields.has("fld001")); // still present in the payload
    REQUIRE(fields.get("fld001").is_null());
    REQUIRE(fields.count() == 2);
}

TEST_CASE("typed getters handle both int and double storage", "[fields]") {
    Fields fields({{"fldI", json(7)}, {"fldD", json(7.5)}});
    REQUIRE(fields.get_long("fldI") == 7);
    REQUIRE(fields.get_double("fldI") == 7.0);
    REQUIRE(fields.get_long("fldD") == 7); // truncating, C# (long) cast parity
    REQUIRE(fields.get_double("fldD") == 7.5);
}

TEST_CASE("typed string getter rejects non-strings", "[fields]") {
    auto fields = make_fields();
    REQUIRE(fields.get_string("fld001") == "hello");
    REQUIRE(fields.get_string("fld002") == std::nullopt); // number, not string
    REQUIRE(fields.get_string("fldMissing") == std::nullopt);
    REQUIRE(fields.get_bool("fld001") == std::nullopt);
}

TEST_CASE("set_strings encodes a string array", "[fields]") {
    Fields fields;
    fields.set_strings("fldL", std::vector<std::string>{"rec1", "rec2"});
    REQUIRE(fields.get("fldL") == json::parse(R"(["rec1","rec2"])"));
    REQUIRE(fields.get_array("fldL")->size() == 2);
}

TEST_CASE("serialization round-trip preserves storage but drops name-to-id", "[fields]") {
    auto fields = make_fields();
    json encoded = fields;
    REQUIRE(encoded == json::parse(R"({"fld001":"hello","fld002":42.0})"));
    auto decoded = encoded.get<Fields>();
    REQUIRE(decoded == fields); // equality is storage-only
    REQUIRE(decoded.name_to_id().empty());
    REQUIRE(decoded.get("Primary Key").is_null()); // mapping gone until re-attached
}

TEST_CASE("missing fields object decodes without throwing", "[fields]") {
    REQUIRE(json(nullptr).get<Fields>().count() == 0);
    REQUIRE(json::object().get<Fields>().count() == 0);
}
