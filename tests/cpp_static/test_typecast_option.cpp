// Per-request typecast forwarding on every write path
// (C# TestTypecastOption parity, 10 cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_model.hpp"
#include "dict_table.hpp"
#include "fake_transport.hpp"
#include "orm_table.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace myairtable {

struct CastModel : AirtableModel<CastModel> {
    static constexpr std::string_view kTableId = "tblCast";
    std::optional<std::string> id{};
    std::optional<DateTime> created_time{};
    std::shared_ptr<AirtableClient> client_{};
    json snapshot_{};
    std::optional<std::string> name{};

    json collect_writable_fields() const {
        json fields = json::object();
        write_field(fields, "fldName", name);
        return fields;
    }
    json collect_computed_fields() const { return json::object(); }
};

inline void from_json(const json& record, CastModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    const json fields = record.contains("fields") ? record.at("fields") : json::object();
    m.name = read_field<std::string>(fields, "fldName");
}

} // namespace myairtable

namespace {
constexpr const char* kOne = R"({"records":[{"id":"rec1","fields":{"fldName":"a"}}]})";

std::shared_ptr<AirtableClient> fast_client(FakeTransport& transport) {
    return std::make_shared<AirtableClient>("app1", "key1", transport.fn(), 0.0, 0.0);
}
json last_body(const FakeTransport& transport) {
    return json::parse(*transport.requests().back().body);
}
} // namespace

TEST_CASE("orm create omits typecast by default", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne);
    OrmTable<CastModel>(fast_client(transport)).create(CastModel{.name = "a"});
    REQUIRE_FALSE(last_body(transport).contains("typecast"));
}

TEST_CASE("orm create emits typecast when set", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne);
    OrmTable<CastModel>(fast_client(transport)).create(CastModel{.name = "a"}, /*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("orm update omits typecast by default", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","fields":{"fldName":"a"}})").respond(200, kOne);
    OrmTable<CastModel> table(fast_client(transport));
    auto m = table.get("rec1");
    m.name = "b";
    table.update(m);
    REQUIRE_FALSE(last_body(transport).contains("typecast"));
}

TEST_CASE("orm update emits typecast when set", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","fields":{"fldName":"a"}})").respond(200, kOne);
    OrmTable<CastModel> table(fast_client(transport));
    auto m = table.get("rec1");
    m.name = "b";
    table.update(m, /*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("orm upsert omits typecast by default", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne);
    OrmTable<CastModel>(fast_client(transport)).upsert(CastModel{.name = "a"}, {"fldName"});
    REQUIRE_FALSE(last_body(transport).contains("typecast"));
}

TEST_CASE("orm upsert emits typecast when set", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne);
    OrmTable<CastModel>(fast_client(transport))
        .upsert(CastModel{.name = "a"}, {"fldName"}, /*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("dict create omits typecast by default and emits when set", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne).respond(200, kOne);
    DictTable table(fast_client(transport), "tblCast");
    table.create(Fields{});
    REQUIRE_FALSE(last_body(transport).contains("typecast"));
    table.create(Fields{}, /*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("dict update omits typecast by default and emits when set", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne).respond(200, kOne);
    DictTable table(fast_client(transport), "tblCast");
    table.update("rec1", Fields{});
    REQUIRE_FALSE(last_body(transport).contains("typecast"));
    table.update("rec1", Fields{}, /*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("model save forwards typecast", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","fields":{"fldName":"a"}})").respond(200, kOne);
    auto m = OrmTable<CastModel>(fast_client(transport)).get("rec1");
    m.name = "b";
    m.save(/*typecast=*/true);
    REQUIRE(last_body(transport).at("typecast") == true);
}

TEST_CASE("typecast=true always accompanies returnFieldsByFieldId", "[typecast]") {
    FakeTransport transport;
    transport.respond(200, kOne);
    OrmTable<CastModel>(fast_client(transport)).create(CastModel{.name = "a"}, /*typecast=*/true);
    const auto body = last_body(transport);
    REQUIRE(body.at("typecast") == true);
    REQUIRE(body.at("returnFieldsByFieldId") == true);
}
