// Bounded multi-id get, empty-diff update partitioning, offset-loop invariants
// (Java TestTableBoundedOps parity, 8 cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_model.hpp"
#include "dict_table.hpp"
#include "fake_transport.hpp"
#include "orm_table.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace myairtable {

struct BoundedModel : AirtableModel<BoundedModel> {
    static constexpr std::string_view kTableId = "tblBounded";
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

inline void from_json(const json& record, BoundedModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    const json fields = record.contains("fields") ? record.at("fields") : json::object();
    m.name = read_field<std::string>(fields, "fldName");
}

} // namespace myairtable

namespace {
std::string envelope(const std::string& id, const std::string& name) {
    return R"({"id":")" + id + R"(","fields":{"fldName":")" + name + R"("}})";
}
std::shared_ptr<AirtableClient> fast_client(FakeTransport& transport) {
    return std::make_shared<AirtableClient>("app1", "key1", transport.fn(), 0.0, 0.0);
}
} // namespace

TEST_CASE("orm multi-get preserves caller order", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, envelope("recB", "b")).respond(200, envelope("recA", "a"));
    OrmTable<BoundedModel> table(fast_client(transport));
    auto models = table.get_many(std::vector<std::string>{"recB", "recA"});
    REQUIRE(models.size() == 2);
    REQUIRE(models[0].id == "recB");
    REQUIRE(models[1].id == "recA");
}

TEST_CASE("multi-get with empty input makes no requests", "[bounded]") {
    FakeTransport transport;
    OrmTable<BoundedModel> table(fast_client(transport));
    REQUIRE(table.get_many(std::vector<std::string>{}).empty());
    REQUIRE(transport.calls() == 0);
}

TEST_CASE("all clean models update without any request", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, envelope("rec1", "a")).respond(200, envelope("rec2", "b"));
    OrmTable<BoundedModel> table(fast_client(transport));
    auto a = table.get_one("rec1");
    auto b = table.get_one("rec2");
    auto updated = table.update_many(std::vector<BoundedModel>{a, b});
    REQUIRE(updated.size() == 2);
    REQUIRE(transport.calls() == 2); // the two gets, no PATCH
}

TEST_CASE("mixed list patches only the dirty model and preserves order", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, envelope("rec1", "a"))
        .respond(200, envelope("rec2", "b"))
        .respond(200, R"({"records":[)" + envelope("rec2", "b2") + "]}");
    OrmTable<BoundedModel> table(fast_client(transport));
    auto clean = table.get_one("rec1");
    auto dirty = table.get_one("rec2");
    dirty.name = "b2";
    auto updated = table.update_many(std::vector<BoundedModel>{clean, dirty});
    REQUIRE(updated.size() == 2);
    REQUIRE(updated[0].id == "rec1"); // clean model in original position
    REQUIRE(updated[1].name == "b2");
    const json body = json::parse(*transport.requests()[2].body);
    REQUIRE(body.at("records").size() == 1); // only the dirty one PATCHed
}

TEST_CASE("update chunks past the batch limit", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, envelope("seed", "s"));
    OrmTable<BoundedModel> table(fast_client(transport));
    auto seed = table.get_one("seed");

    std::vector<BoundedModel> models;
    json batch1 = json::array();
    json batch2 = json::array();
    for (int i = 0; i < 12; ++i) {
        auto m = seed;
        m.id = "rec" + std::to_string(i);
        m.name = "changed" + std::to_string(i);
        models.push_back(m);
        (i < 10 ? batch1 : batch2).push_back(json::parse(envelope(*m.id, *m.name)));
    }
    transport.respond(200, json{{"records", batch1}}.dump())
        .respond(200, json{{"records", batch2}}.dump());
    auto updated = table.update_many(models);
    REQUIRE(updated.size() == 12);
    REQUIRE(transport.calls() == 3); // 1 get + 2 PATCH chunks
    REQUIRE(json::parse(*transport.requests()[1].body).at("records").size() == 10);
    REQUIRE(json::parse(*transport.requests()[2].body).at("records").size() == 2);
}

TEST_CASE("orm get_many follows offset, merges pages in order, terminates", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[)" + envelope("rec1", "a") + R"(],"offset":"page2"})")
        .respond(200, R"({"records":[)" + envelope("rec2", "b") + "]}");
    OrmTable<BoundedModel> table(fast_client(transport));
    auto models = table.get_many();
    REQUIRE(models.size() == 2);
    REQUIRE(models[0].id == "rec1");
    REQUIRE(models[1].id == "rec2");
    REQUIRE(transport.calls() == 2);
    REQUIRE(transport.requests()[1].url.find("offset=page2") != std::string::npos);
}

TEST_CASE("dict get_many follows offset and terminates", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[{"id":"r1","fields":{}}],"offset":"tok"})")
        .respond(200, R"({"records":[{"id":"r2","fields":{}}]})");
    DictTable table(fast_client(transport), "tblBounded");
    REQUIRE(table.get_many().size() == 2);
    REQUIRE(transport.calls() == 2);
}

TEST_CASE("remove chunks past the batch limit", "[bounded]") {
    FakeTransport transport;
    transport.respond(200, "{}").respond(200, "{}");
    OrmTable<BoundedModel> table(fast_client(transport));
    std::vector<std::string> ids;
    for (int i = 0; i < 12; ++i) {
        ids.push_back("rec" + std::to_string(i));
    }
    table.delete_many(ids);
    REQUIRE(transport.calls() == 2); // 10 + 2
}
