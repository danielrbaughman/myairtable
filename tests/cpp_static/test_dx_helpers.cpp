// DX helpers: require_id/require_client, sum-type value accessors, view query
// sugar (Java TestDxHelpers parity, 12 cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_model.hpp"
#include "airtable_query.hpp"
#include "fake_transport.hpp"
#include "maybe_special_or_error.hpp"
#include "vec_or_value.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace myairtable {

struct DxModel : AirtableModel<DxModel> {
    static constexpr std::string_view kTableId = "tblDx";
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

inline void from_json(const json& record, DxModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    const json fields = record.contains("fields") ? record.at("fields") : json::object();
    m.name = read_field<std::string>(fields, "fldName");
}

} // namespace myairtable

TEST_CASE("require_id returns the server-assigned id", "[dx]") {
    auto m = DxModel{.id = "rec42"};
    REQUIRE(m.require_id() == "rec42");
}

TEST_CASE("require_id throws UNSAVED_MODEL when id is absent or empty", "[dx]") {
    REQUIRE_THROWS_AS(DxModel{}.require_id(), ApiError);
    REQUIRE_THROWS_AS(DxModel{.id = ""}.require_id(), ApiError);
}

TEST_CASE("require_client throws DETACHED_MODEL without a client", "[dx]") {
    try {
        DxModel{.id = "rec1"}.require_client();
        FAIL("expected ApiError");
    } catch (const ApiError& e) {
        REQUIRE(e.code == "DETACHED_MODEL");
    }
}

TEST_CASE("value() is nullopt for special and error variants", "[dx]") {
    REQUIRE(MaybeSpecialOrError<double>(3.5).value() == 3.5);
    REQUIRE(MaybeSpecialOrError<double>(SpecialNumber{"NaN"}).value() == std::nullopt);
    REQUIRE(MaybeSpecialOrError<double>(ErrorValue{"#ERROR!"}).value() == std::nullopt);
}

TEST_CASE("optional-wrapped computed fields chain through value()", "[dx]") {
    // The generated member shape: optional<MaybeSpecialOrError<T>>.
    std::optional<MaybeSpecialOrError<int64_t>> absent;
    std::optional<MaybeSpecialOrError<int64_t>> present = MaybeSpecialOrError<int64_t>(int64_t{9});
    REQUIRE_FALSE(absent.has_value());
    REQUIRE(present->value() == 9);
}

TEST_CASE("clean_values unwraps the single shape", "[dx]") {
    auto single = json("only").get<VecOrValue<std::string>>();
    REQUIRE(single.clean_values() == std::vector<std::string>{"only"});
}

TEST_CASE("clean_values drops nulls, specials, and errors from the list shape", "[dx]") {
    auto v = json::parse(R"([1, null, {"specialValue":"NaN"}, 2, {"error":"#ERROR!"}])")
                 .get<VecOrValue<MaybeSpecialOrError<int64_t>>>();
    REQUIRE(v.clean_values() == std::vector<int64_t>{1, 2});
}

TEST_CASE("values preserves the raw nullable shape clean_values flattens", "[dx]") {
    auto v = json::parse(R"(["a", null])").get<VecOrValue<std::string>>();
    REQUIRE(v.values().size() == 2);
    REQUIRE(v.clean_values().size() == 1);
}

TEST_CASE("query with a view id encodes the view param", "[dx]") {
    auto params = AirtableQuery{.view = "viwABC"}.to_parameters();
    bool found = false;
    for (const auto& [key, value] : params) {
        if (key == "view" && value == "viwABC") {
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("assigning a new view overrides the previous one", "[dx]") {
    AirtableQuery query{.view = "viwOld"};
    query.view = "viwNew";
    const auto params = query.to_parameters();
    for (const auto& [key, value] : params) {
        if (key == "view") {
            REQUIRE(value == "viwNew");
        }
    }
}

TEST_CASE("is_new distinguishes fresh from persisted models", "[dx]") {
    REQUIRE(DxModel{}.is_new());
    REQUIRE_FALSE(DxModel{.id = "rec1"}.is_new());
}

TEST_CASE("fetch returns a fresh instance from the server", "[dx]") {
    FakeTransport transport;
    transport.respond(200, R"({"id":"rec1","fields":{"fldName":"latest"}})");
    auto client = std::make_shared<AirtableClient>("app1", "key1", transport.fn(), 0.0, 0.0);
    auto stale = DxModel{.id = "rec1", .client_ = client, .name = "stale"};
    auto fresh = stale.fetch();
    REQUIRE(fresh.name == "latest");
    REQUIRE(stale.name == "stale"); // original untouched
}
