// Computed special/error-value decode + sum-type round-trips
// (Java TestSpecialErrorDecoding parity, ~25 cases).
#include <catch2/catch_test_macros.hpp>

#include "vec_or_value.hpp"

using namespace myairtable;

// ---- SpecialNumber / ErrorValue carriers ------------------------------------

TEST_CASE("special number accepts object form", "[special-error]") {
    auto s = json::parse(R"({"specialValue":"Infinity"})").get<SpecialNumber>();
    REQUIRE(s.special_value == "Infinity");
}

TEST_CASE("special number rejects array form", "[special-error]") {
    REQUIRE_THROWS(json::parse(R"(["NaN"])").get<SpecialNumber>());
}

TEST_CASE("error value accepts object form", "[special-error]") {
    auto e = json::parse(R"({"error":"#ERROR!"})").get<ErrorValue>();
    REQUIRE(e.error == "#ERROR!");
}

TEST_CASE("error value rejects array form", "[special-error]") {
    REQUIRE_THROWS(json::parse(R"([{"error":"#ERROR!"}])").get<ErrorValue>());
}

// ---- MaybeSpecialOrError ------------------------------------------------------

TEST_CASE("maybe decodes value", "[special-error]") {
    auto v = json(42.5).get<MaybeSpecialOrError<double>>();
    REQUIRE(v.is_value());
    REQUIRE(v.value() == 42.5);
}

TEST_CASE("maybe decodes special", "[special-error]") {
    auto v = json::parse(R"({"specialValue":"NaN"})").get<MaybeSpecialOrError<double>>();
    REQUIRE(v.is_special());
    REQUIRE(v.special()->special_value == "NaN");
    REQUIRE(v.value() == std::nullopt);
}

TEST_CASE("maybe decodes error", "[special-error]") {
    auto v = json::parse(R"({"error":"#ERROR!"})").get<MaybeSpecialOrError<double>>();
    REQUIRE(v.is_error());
    REQUIRE(v.error()->error == "#ERROR!");
}

TEST_CASE("maybe string parses plain string", "[special-error]") {
    auto v = json("hello").get<MaybeSpecialOrError<std::string>>();
    REQUIRE(v.value() == "hello");
}

TEST_CASE("maybe string rejects lookup array", "[special-error]") {
    REQUIRE_THROWS(json::parse(R"(["a","b"])").get<MaybeSpecialOrError<std::string>>());
}

TEST_CASE("maybe helpers: value/special/error accessors are disjoint", "[special-error]") {
    auto value = MaybeSpecialOrError<int64_t>(int64_t{7});
    REQUIRE(value.is_value());
    REQUIRE_FALSE(value.is_special());
    REQUIRE_FALSE(value.is_error());
    REQUIRE(value.value() == 7);
    REQUIRE(value.special() == std::nullopt);
    REQUIRE(value.error() == std::nullopt);

    auto special = MaybeSpecialOrError<int64_t>(SpecialNumber{"-Infinity"});
    REQUIRE(special.is_special());
    REQUIRE(special.value() == std::nullopt);

    auto error = MaybeSpecialOrError<int64_t>(ErrorValue{"#ERROR!"});
    REQUIRE(error.is_error());
    REQUIRE(error.value() == std::nullopt);
}

// ---- VecOrValue ---------------------------------------------------------------

TEST_CASE("vec-or-value single", "[special-error]") {
    auto v = json("one").get<VecOrValue<std::string>>();
    REQUIRE(v.is_single());
    REQUIRE(v.value() == "one");
    REQUIRE(v.values().size() == 1);
}

TEST_CASE("vec-or-value multiple", "[special-error]") {
    auto v = json::parse(R"(["a","b","c"])").get<VecOrValue<std::string>>();
    REQUIRE(v.is_multiple());
    REQUIRE(v.values().size() == 3);
    REQUIRE(v.values()[1] == "b");
    REQUIRE(v.value() == std::nullopt);
}

TEST_CASE("vec-or-value nullable items preserved", "[special-error]") {
    auto v = json::parse(R"(["a",null,"c"])").get<VecOrValue<std::string>>();
    auto items = v.values();
    REQUIRE(items.size() == 3);
    REQUIRE(items[0] == "a");
    REQUIRE(items[1] == std::nullopt);
    REQUIRE(items[2] == "c");
    REQUIRE(v.clean_values() == std::vector<std::string>{"a", "c"});
}

TEST_CASE("vec-or-value all nulls", "[special-error]") {
    auto v = json::parse(R"([null,null])").get<VecOrValue<std::string>>();
    REQUIRE(v.values().size() == 2);
    REQUIRE(v.clean_values().empty());
}

TEST_CASE("vec-or-value empty", "[special-error]") {
    auto v = json::parse("[]").get<VecOrValue<MaybeSpecialOrError<std::string>>>();
    REQUIRE(v.is_multiple());
    REQUIRE(v.values().empty());
}

TEST_CASE("vec-or-value special-number object decodes as single", "[special-error]") {
    auto v =
        json::parse(R"({"specialValue":"NaN"})").get<VecOrValue<MaybeSpecialOrError<double>>>();
    REQUIRE(v.is_single());
    REQUIRE(v.value()->special()->special_value == "NaN");
}

TEST_CASE("vec-or-value error object decodes as single", "[special-error]") {
    auto v = json::parse(R"({"error":"#ERROR!"})").get<VecOrValue<MaybeSpecialOrError<double>>>();
    REQUIRE(v.is_single());
    REQUIRE(v.value()->error()->error == "#ERROR!");
}

TEST_CASE("vec-or-value mixed array preserves every element kind", "[special-error]") {
    auto v = json::parse(R"([1, {"specialValue":"NaN"}, {"error":"#ERROR!"}, null])")
                 .get<VecOrValue<MaybeSpecialOrError<int64_t>>>();
    auto items = v.values();
    REQUIRE(items.size() == 4);
    REQUIRE(items[0]->value() == 1);
    REQUIRE(items[1]->special()->special_value == "NaN");
    REQUIRE(items[2]->error()->error == "#ERROR!");
    REQUIRE(items[3] == std::nullopt);
    // clean_values flattens the nested wrapper: nulls, specials, errors dropped.
    REQUIRE(v.clean_values() == std::vector<int64_t>{1});
}

// ---- Round-trips ---------------------------------------------------------------

TEST_CASE("special number round trip", "[special-error]") {
    SpecialNumber original{"NaN"};
    json encoded = original;
    REQUIRE(encoded.dump() == R"({"specialValue":"NaN"})");
    REQUIRE(encoded.get<SpecialNumber>() == original);
}

TEST_CASE("maybe encodes untagged", "[special-error]") {
    REQUIRE(json(MaybeSpecialOrError<int64_t>(int64_t{7})).dump() == "7");
    REQUIRE(json(MaybeSpecialOrError<int64_t>(ErrorValue{"#ERROR!"})).dump() ==
            R"({"error":"#ERROR!"})");
}

TEST_CASE("vec-or-value serializes multiple with nulls", "[special-error]") {
    VecOrValue<MaybeSpecialOrError<std::string>> v(
        std::vector<std::optional<MaybeSpecialOrError<std::string>>>{
            MaybeSpecialOrError<std::string>(std::string("a")), std::nullopt});
    REQUIRE(json(v).dump() == R"(["a",null])");
}

TEST_CASE("nested vec-or-value full round trip", "[special-error]") {
    const auto* wire = R"(["ok",{"specialValue":"NaN"},null])";
    auto decoded = json::parse(wire).get<VecOrValue<MaybeSpecialOrError<std::string>>>();
    REQUIRE(json(decoded) == json::parse(wire));
}
