// CRTP AirtableModel + OrmTable behavior over a hand-written model shaped
// exactly like generator output (Kotlin TestSerializableModel parity).
#include <catch2/catch_test_macros.hpp>

#include "airtable_model.hpp"
#include "fake_transport.hpp"
#include "maybe_special_or_error.hpp"
#include "orm_table.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace myairtable {

// The exact shape write_models emits (see src/generators/cpp.py F4.2).
struct ProbeModel : AirtableModel<ProbeModel> {
    static constexpr std::string_view kTableId = "tblProbe";

    std::optional<std::string> id{};
    std::optional<DateTime> created_time{};
    std::shared_ptr<AirtableClient> client_{};
    json snapshot_{};

    std::optional<std::string> name{};                         // fldName (writable)
    std::optional<double> score{};                             // fldScore (writable)
    std::optional<MaybeSpecialOrError<int64_t>> auto_number{}; // fldAuto (computed)

    json collect_writable_fields() const {
        json fields = json::object();
        write_field(fields, "fldName", name);
        write_field(fields, "fldScore", score);
        return fields;
    }
    json collect_computed_fields() const {
        json fields = json::object();
        write_field(fields, "fldAuto", auto_number);
        return fields;
    }
};

inline void from_json(const json& record, ProbeModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    if (record.contains("createdTime")) {
        m.created_time = record.at("createdTime").get<DateTime>();
    }
    const json fields = record.contains("fields") ? record.at("fields") : json::object();
    m.name = read_field<std::string>(fields, "fldName");
    m.score = read_field<double>(fields, "fldScore");
    m.auto_number = read_field<MaybeSpecialOrError<int64_t>>(fields, "fldAuto");
}

} // namespace myairtable

namespace {
constexpr const char* kEnvelope =
    R"({"id":"rec1","createdTime":"2024-01-15T10:30:00.000Z","fields":{"fldName":"a","fldScore":1.0,"fldAuto":7}})";

std::shared_ptr<AirtableClient> fast_client(FakeTransport& transport) {
    return std::make_shared<AirtableClient>("app1", "key1", transport.fn(), 0.0, 0.0);
}
} // namespace

TEST_CASE("designated-init model is new and detached", "[model]") {
    auto m = ProbeModel{.name = "x"};
    REQUIRE(m.is_new());
    REQUIRE_THROWS_AS(m.require_id(), ApiError);
    REQUIRE_THROWS_AS(m.require_client(), ApiError);
    REQUIRE_THROWS_AS(m.save(), ApiError);
    REQUIRE_THROWS_AS(m.fetch(), ApiError);
    REQUIRE_THROWS_AS(m.remove(), ApiError);
}

TEST_CASE("table decode attaches client and starts clean", "[model]") {
    FakeTransport transport;
    transport.respond(200, kEnvelope);
    OrmTable<ProbeModel> table(fast_client(transport));
    auto m = table.get_one("rec1");
    REQUIRE(m.id == "rec1");
    REQUIRE(m.created_time->epoch_millis() == 1'705'314'600'000);
    REQUIRE(m.name == "a");
    REQUIRE(m.auto_number->value() == 7);
    REQUIRE(m.client_ != nullptr);
    REQUIRE(m.dirty_fields().empty()); // snapshot taken on decode
}

TEST_CASE("dirty diff tracks changes and clears; computed never included", "[model]") {
    FakeTransport transport;
    transport.respond(200, kEnvelope);
    auto m = OrmTable<ProbeModel>(fast_client(transport)).get_one("rec1");

    m.name = "b";
    m.auto_number = MaybeSpecialOrError<int64_t>(int64_t{999}); // R21: silently dropped
    auto dirty = m.dirty_fields();
    REQUIRE(dirty.size() == 1);
    REQUIRE(dirty.at("fldName") == "b");

    m.score = std::nullopt; // clearing is a change: explicit JSON null
    REQUIRE(m.dirty_fields().at("fldScore").is_null());
}

TEST_CASE("to_create_fields drops nulls; to_record merges computed", "[model]") {
    auto m = ProbeModel{.name = "x"};
    REQUIRE(m.to_create_fields() == json::parse(R"({"fldName":"x"})"));
    m.auto_number = MaybeSpecialOrError<int64_t>(int64_t{5});
    auto record = m.to_record();
    REQUIRE(record.at("fldName") == "x");
    REQUIRE(record.at("fldAuto") == 5);
}

TEST_CASE("table update PATCHes dirty fields only and skips clean models", "[model]") {
    FakeTransport transport;
    transport
        .respond(200, kEnvelope) // get (single-record envelope)
        .respond(200, R"({"records":[)" + std::string(kEnvelope) + "]}"); // collection PATCH
    auto client = fast_client(transport);
    OrmTable<ProbeModel> table(client);
    auto m = table.get_one("rec1");

    // Clean model: update() must NOT issue a PATCH.
    auto same = table.update_one(m);
    REQUIRE(transport.calls() == 1);

    m.name = "changed";
    table.update_one(m);
    REQUIRE(transport.calls() == 2);
    const json body = json::parse(*transport.requests()[1].body);
    REQUIRE(body.at("records").size() == 1);
    REQUIRE(body.at("records")[0].at("id") == "rec1");
    REQUIRE(body.at("records")[0].at("fields") == json::parse(R"({"fldName":"changed"})"));
    REQUIRE_FALSE(body.contains("typecast"));
}

TEST_CASE("model save routes through the table with dirty fields", "[model]") {
    FakeTransport transport;
    transport.respond(200, kEnvelope)
        .respond(200, R"({"records":[)" + std::string(kEnvelope) + "]}");
    auto m = OrmTable<ProbeModel>(fast_client(transport)).get_one("rec1");
    m.score = 2.0;
    auto saved = m.save();
    REQUIRE(transport.calls() == 2);
    REQUIRE(transport.requests()[1].method == "PATCH");
    REQUIRE(saved.dirty_fields().empty()); // fresh, freshly-snapshotted instance
}

TEST_CASE("create sends non-null writables and returns decoded models", "[model]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[)" + std::string(kEnvelope) + "]}");
    OrmTable<ProbeModel> table(fast_client(transport));
    auto created = table.create_one(ProbeModel{.name = "a", .score = 1.0});
    REQUIRE(created.id == "rec1");
    const json body = json::parse(*transport.requests()[0].body);
    REQUIRE(body.at("records")[0].at("fields") == json::parse(R"({"fldName":"a","fldScore":1.0})"));
    REQUIRE(body.at("returnFieldsByFieldId") == true);
}

TEST_CASE("upsert reports was_created from createdRecords", "[model]") {
    FakeTransport transport;
    transport.respond(200, R"({"records":[)" + std::string(kEnvelope) +
                               R"(],"createdRecords":["rec1"]})");
    OrmTable<ProbeModel> table(fast_client(transport));
    auto result = table.upsert(ProbeModel{.name = "a"}, {"fldName"});
    REQUIRE(result.was_created);
    REQUIRE(result.model.id == "rec1");
    const json body = json::parse(*transport.requests()[0].body);
    REQUIRE(body.at("performUpsert").at("fieldsToMergeOn") == json::parse(R"(["fldName"])"));
}

TEST_CASE("model remove deletes by id", "[model]") {
    FakeTransport transport;
    transport.respond(200, kEnvelope).respond(200, R"({"deleted":true})");
    auto m = OrmTable<ProbeModel>(fast_client(transport)).get_one("rec1");
    m.remove();
    REQUIRE(transport.requests()[1].method == "DELETE");
    REQUIRE(transport.requests()[1].url.find("tblProbe/rec1") != std::string::npos);
}

TEST_CASE("decode failure surfaces as DecodingError", "[model]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","fields":{"fldScore":"not-a-number"}})");
    OrmTable<ProbeModel> table(fast_client(transport));
    REQUIRE_THROWS_AS(table.get_one("rec1"), DecodingError);
}
