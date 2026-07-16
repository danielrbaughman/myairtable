// Value coercion helpers v/n/s/a/an/as/is_truthy/is_equal/is_blank
// (Java TestValueCoercion parity, ~19 cases).
#include <catch2/catch_test_macros.hpp>

#include "runtime.hpp"

using namespace myairtable;
namespace rt = myairtable::runtime;

// ---- v() boxing -----------------------------------------------------------------

TEST_CASE("v boxes null and scalars", "[coercion]") {
    REQUIRE(rt::v(nullptr).is_null());
    REQUIRE(rt::v(true) == json(true));
    REQUIRE(rt::v(42) == json(42));
    REQUIRE(rt::v(int64_t{42}) == json(42));
    REQUIRE(rt::v(3.14) == json(3.14));
    REQUIRE(rt::v("text") == json("text"));
    REQUIRE(rt::v(std::string("text")) == json("text"));
}

TEST_CASE("v distinguishes integer and double storage", "[coercion]") {
    REQUIRE(rt::v(42).is_number_integer());
    REQUIRE(rt::v(42.0).is_number_float());
}

TEST_CASE("v passes json through untouched", "[coercion]") {
    json original = json::parse(R"({"a":[1,2]})");
    REQUIRE(rt::v(original) == original);
}

TEST_CASE("v boxes optional: engaged, empty", "[coercion]") {
    REQUIRE(rt::v(std::optional<std::string>("x")) == json("x"));
    REQUIRE(rt::v(std::optional<std::string>{}).is_null());
    REQUIRE(rt::v(std::optional<double>{}).is_null());
}

TEST_CASE("v boxes vectors as arrays", "[coercion]") {
    REQUIRE(rt::v(std::vector<std::string>{"a", "b"}) == json::parse(R"(["a","b"])"));
    REQUIRE(rt::v(std::vector<double>{}) == json::array());
}

// ---- n() ----------------------------------------------------------------------------

TEST_CASE("n coerces blank to zero", "[coercion]") {
    REQUIRE(rt::n(json(nullptr)) == 0.0);
}

TEST_CASE("n reads numbers and numeric strings", "[coercion]") {
    REQUIRE(rt::n(json(42)) == 42.0);
    REQUIRE(rt::n(json(3.5)) == 3.5);
    REQUIRE(rt::n(json("42")) == 42.0);
    REQUIRE(rt::n(json("  3.5  ")) == 3.5);
    REQUIRE(rt::n(json("-1e2")) == -100.0);
}

TEST_CASE("n coerces non-numeric strings and junk to zero", "[coercion]") {
    REQUIRE(rt::n(json("abc")) == 0.0);
    REQUIRE(rt::n(json("42abc")) == 0.0);
    REQUIRE(rt::n(json("")) == 0.0);
    REQUIRE(rt::n(json::object()) == 0.0);
}

TEST_CASE("n coerces booleans and arrays", "[coercion]") {
    REQUIRE(rt::n(json(true)) == 1.0);
    REQUIRE(rt::n(json(false)) == 0.0);
    REQUIRE(rt::n(json::parse("[7, 9]")) == 7.0); // first element
    REQUIRE(rt::n(json::array()) == 0.0);
}

// ---- s() -----------------------------------------------------------------------------

TEST_CASE("s coerces blank to empty string", "[coercion]") {
    REQUIRE(rt::s(json(nullptr)).empty());
}

TEST_CASE("s renders whole numbers without decimal point", "[coercion]") {
    REQUIRE(rt::s(json(42.0)) == "42");
    REQUIRE(rt::s(json(42)) == "42");
    REQUIRE(rt::s(json(-7.0)) == "-7");
    REQUIRE(rt::s(json(0)) == "0");
}

TEST_CASE("s renders decimals shortest-round-trip", "[coercion]") {
    REQUIRE(rt::s(json(3.14)) == "3.14");
    REQUIRE(rt::s(json(0.5)) == "0.5");
}

TEST_CASE("s renders booleans as 1 and 0", "[coercion]") {
    REQUIRE(rt::s(json(true)) == "1");
    REQUIRE(rt::s(json(false)) == "0");
}

TEST_CASE("s joins arrays with comma-space", "[coercion]") {
    REQUIRE(rt::s(json::parse(R"(["a","b","c"])")) == "a, b, c");
    REQUIRE(rt::s(json::parse("[1.0, 2.0]")) == "1, 2");
    REQUIRE(rt::s(json::array()).empty());
}

// ---- a()/an()/as() -----------------------------------------------------------------------

TEST_CASE("a flattens one level and drops nulls", "[coercion]") {
    std::vector<json> args{json(1), json(nullptr), json::parse("[2, 3]"), json("x")};
    auto flat = rt::a(args);
    REQUIRE(flat.size() == 4);
    REQUIRE(flat[0] == json(1));
    REQUIRE(flat[1] == json(2));
    REQUIRE(flat[2] == json(3));
    REQUIRE(flat[3] == json("x"));
}

TEST_CASE("a does not recurse past one level", "[coercion]") {
    std::vector<json> args{json::parse("[[1, 2], 3]")};
    auto flat = rt::a(args);
    REQUIRE(flat.size() == 2);
    REQUIRE(flat[0] == json::parse("[1, 2]"));
}

TEST_CASE("an and as map the coercions over flattened args", "[coercion]") {
    std::vector<json> args{json("2"), json::parse("[3, true]"), json(nullptr)};
    REQUIRE(rt::an(args) == std::vector<double>{2.0, 3.0, 1.0});
    REQUIRE(rt::as(args) == std::vector<std::string>{"2", "3", "1"});
}

// ---- is_truthy() -------------------------------------------------------------------------

TEST_CASE("is_truthy falsy set: blank, empty string, zero, false, empties, NaN", "[coercion]") {
    REQUIRE_FALSE(rt::is_truthy(json(nullptr)));
    REQUIRE_FALSE(rt::is_truthy(json("")));
    REQUIRE_FALSE(rt::is_truthy(json(0)));
    REQUIRE_FALSE(rt::is_truthy(json(0.0)));
    REQUIRE_FALSE(rt::is_truthy(json(false)));
    REQUIRE_FALSE(rt::is_truthy(json::array()));
    REQUIRE_FALSE(rt::is_truthy(json::object()));
    REQUIRE_FALSE(rt::is_truthy(json(std::nan(""))));
}

TEST_CASE("is_truthy truthy set", "[coercion]") {
    REQUIRE(rt::is_truthy(json("x")));
    REQUIRE(rt::is_truthy(json(1)));
    REQUIRE(rt::is_truthy(json(-0.5)));
    REQUIRE(rt::is_truthy(json(true)));
    REQUIRE(rt::is_truthy(json::parse("[0]")));
    REQUIRE(rt::is_truthy(json::parse(R"({"k":1})")));
}

// ---- is_equal() ---------------------------------------------------------------------------

TEST_CASE("is_equal: blanks equal each other only", "[coercion]") {
    REQUIRE(rt::is_equal(json(nullptr), json(nullptr)));
    REQUIRE_FALSE(rt::is_equal(json(nullptr), json("")));
    REQUIRE_FALSE(rt::is_equal(json(0), json(nullptr)));
}

TEST_CASE("is_equal: numbers compare numerically across int/double storage", "[coercion]") {
    REQUIRE(rt::is_equal(json(42), json(42.0)));
    REQUIRE(rt::is_equal(json(5.0), json(5)));
    REQUIRE_FALSE(rt::is_equal(json(5), json(6)));
}

TEST_CASE("is_equal: cross-type falls back to string coercion", "[coercion]") {
    REQUIRE(rt::is_equal(json("5"), json(5)));  // S("5") == S(5)
    REQUIRE(rt::is_equal(json(true), json(1))); // "1" == "1"
    REQUIRE_FALSE(rt::is_equal(json("a"), json(5)));
}

TEST_CASE("is_blank matches JSON null only", "[coercion]") {
    REQUIRE(rt::is_blank(json(nullptr)));
    REQUIRE_FALSE(rt::is_blank(json("")));
    REQUIRE_FALSE(rt::is_blank(json(0)));
}
