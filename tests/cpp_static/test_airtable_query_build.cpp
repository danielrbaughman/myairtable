// Query/list-records parameter building (Java TestAirtableQueryBuild parity, 12 cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_query.hpp"

using namespace myairtable;
using Params = std::vector<std::pair<std::string, std::string>>;

TEST_CASE("default query only emits returnFieldsByFieldId", "[query]") {
    REQUIRE(AirtableQuery{}.to_parameters() == Params{{"returnFieldsByFieldId", "true"}});
}

TEST_CASE("formula encodes as filterByFormula", "[query]") {
    auto params = AirtableQuery{.formula = "{Name} = 'x'"}.to_parameters();
    REQUIRE(params.front() ==
            std::pair<std::string, std::string>{"filterByFormula", "{Name} = 'x'"});
}

TEST_CASE("empty formula is omitted", "[query]") {
    REQUIRE(AirtableQuery{.formula = ""}.to_parameters() ==
            Params{{"returnFieldsByFieldId", "true"}});
}

TEST_CASE("fields encode as repeated array params", "[query]") {
    auto params = AirtableQuery{.fields = {"fldA", "fldB"}}.to_parameters();
    REQUIRE(params[0] == std::pair<std::string, std::string>{"fields[]", "fldA"});
    REQUIRE(params[1] == std::pair<std::string, std::string>{"fields[]", "fldB"});
}

TEST_CASE("sort encodes indexed field and direction", "[query]") {
    auto params = AirtableQuery{.sorts = {{.field = "Name"},
                                          {.field = "Age", .direction = SortDirection::Desc}}}
                      .to_parameters();
    REQUIRE(params[0] == std::pair<std::string, std::string>{"sort[0][field]", "Name"});
    REQUIRE(params[1] == std::pair<std::string, std::string>{"sort[0][direction]", "asc"});
    REQUIRE(params[2] == std::pair<std::string, std::string>{"sort[1][field]", "Age"});
    REQUIRE(params[3] == std::pair<std::string, std::string>{"sort[1][direction]", "desc"});
}

TEST_CASE("maxRecords and pageSize encode", "[query]") {
    auto params = AirtableQuery{.max_records = 10, .page_size = 5}.to_parameters();
    REQUIRE(std::find(params.begin(), params.end(),
                      std::pair<std::string, std::string>{"maxRecords", "10"}) != params.end());
    REQUIRE(std::find(params.begin(), params.end(),
                      std::pair<std::string, std::string>{"pageSize", "5"}) != params.end());
}

TEST_CASE("view encodes and empty view is omitted", "[query]") {
    auto with_view = AirtableQuery{.view = "viwXYZ"}.to_parameters();
    REQUIRE(std::find(with_view.begin(), with_view.end(),
                      std::pair<std::string, std::string>{"view", "viwXYZ"}) != with_view.end());
    REQUIRE(AirtableQuery{.view = ""}.to_parameters() == Params{{"returnFieldsByFieldId", "true"}});
}

TEST_CASE("returnFieldsByFieldId can be disabled", "[query]") {
    REQUIRE(AirtableQuery{.return_fields_by_field_id = false}.to_parameters().empty());
}

TEST_CASE("cellFormat only emitted when not json", "[query]") {
    REQUIRE(AirtableQuery{}.to_parameters() == Params{{"returnFieldsByFieldId", "true"}});
    auto params = AirtableQuery{.cell_format = "string"}.to_parameters();
    REQUIRE(std::find(params.begin(), params.end(),
                      std::pair<std::string, std::string>{"cellFormat", "string"}) != params.end());
}

TEST_CASE("timeZone and userLocale encode", "[query]") {
    auto params =
        AirtableQuery{.time_zone = "America/Chicago", .user_locale = "en-us"}.to_parameters();
    REQUIRE(std::find(params.begin(), params.end(),
                      std::pair<std::string, std::string>{"timeZone", "America/Chicago"}) !=
            params.end());
    REQUIRE(std::find(params.begin(), params.end(),
                      std::pair<std::string, std::string>{"userLocale", "en-us"}) != params.end());
}

TEST_CASE("combined query emits expected parameter count", "[query]") {
    auto params = AirtableQuery{.formula = "{A} = 1",
                                .sorts = {{.field = "A"}},
                                .fields = {"fldA", "fldB"},
                                .max_records = 100,
                                .page_size = 50,
                                .view = "viw1",
                                .time_zone = "America/Chicago",
                                .user_locale = "en-us"}
                      .to_parameters();
    // 1 formula + 2 fields + 2 sort + 1 max + 1 page + 1 view + 1 rfbfi + 1 tz + 1 locale
    REQUIRE(params.size() == 11);
}

TEST_CASE("copy semantics produce independent queries", "[query]") {
    AirtableQuery original{.formula = "{A} = 1"};
    AirtableQuery copy = original;
    copy.formula = "{B} = 2";
    copy.max_records = 5;
    REQUIRE(original.formula == "{A} = 1");
    REQUIRE(original.max_records == std::nullopt);
    REQUIRE(original != copy);
}
