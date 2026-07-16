// Harness smoke test: proves the CMake + Catch2 + header-only-runtime wiring
// (include path, C++20 mode, vendored nlohmann) before any real suite lands.
#include <catch2/catch_test_macros.hpp>

#include "airtable_json.hpp"
#include "my_airtable_runtime_info.hpp"

TEST_CASE("runtime version constant is wired", "[smoke]") {
    REQUIRE(myairtable::kVersion == "0.1.0");
}

TEST_CASE("vendored nlohmann json round-trips through owned helpers", "[smoke]") {
    const auto fields = myairtable::json::parse(R"({"fldA": 42.0, "fldB": null})");
    REQUIRE(myairtable::read_field<double>(fields, "fldA") == 42.0);
    REQUIRE_FALSE(myairtable::read_field<double>(fields, "fldB").has_value());
    REQUIRE_FALSE(myairtable::read_field<double>(fields, "fldMissing").has_value());
}
