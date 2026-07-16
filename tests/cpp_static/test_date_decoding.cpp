// Date/date-only decoding + duration codec + tz vendoring
// (Java/Kotlin TestDateDecoding parity + the Java duration codec cases).
#include <catch2/catch_test_macros.hpp>

#include "airtable_date.hpp"
#include "airtable_tz.hpp"

using namespace myairtable;
namespace rt = myairtable::runtime;

namespace {
DateTime decode(const std::string& raw) {
    return json(raw).get<DateTime>();
}
} // namespace

TEST_CASE("full ISO 8601 with fractional seconds decodes", "[dates]") {
    REQUIRE(decode("2024-01-15T10:30:00.000Z").epoch_millis() == 1'705'314'600'000);
    REQUIRE(decode("2024-01-15T10:30:00.123Z").epoch_millis() == 1'705'314'600'123);
}

TEST_CASE("ISO 8601 without fractional seconds decodes", "[dates]") {
    REQUIRE(decode("2024-01-15T10:30:00Z").epoch_millis() == 1'705'314'600'000);
    // Bare (no zone designator) assumes UTC.
    REQUIRE(decode("2024-01-15T10:30:00").epoch_millis() == 1'705'314'600'000);
}

TEST_CASE("date-only decodes as UTC midnight", "[dates]") {
    REQUIRE(decode("2024-01-15").epoch_millis() == 1'705'276'800'000);
}

TEST_CASE("garbage date string throws DecodingError", "[dates]") {
    REQUIRE_THROWS_AS(decode("not-a-date"), DecodingError);
}

TEST_CASE("parser recognizes all supported shapes and only those", "[dates]") {
    REQUIRE(try_parse_datetime("2024-01-15T10:30:00.123Z").has_value());
    REQUIRE(try_parse_datetime("2024-01-15T10:30:00+02:00").has_value());
    REQUIRE(try_parse_datetime("2024-01-15").has_value());
    REQUIRE_FALSE(try_parse_datetime("01/15/2024").has_value());
    REQUIRE_FALSE(try_parse_datetime("").has_value());
    REQUIRE_FALSE(try_parse_datetime("2024-13-01").has_value());
    REQUIRE_FALSE(try_parse_datetime("2024-01-15T25:00:00Z").has_value());
    REQUIRE_FALSE(try_parse_datetime("2024-01-15Tgarbage").has_value());
}

TEST_CASE("offset form normalizes to UTC", "[dates]") {
    REQUIRE(decode("2024-01-15T12:30:00+02:00") == decode("2024-01-15T10:30:00Z"));
    REQUIRE(decode("2024-01-15T08:30:00-02:00") == decode("2024-01-15T10:30:00Z"));
}

TEST_CASE("encode produces ISO 8601 UTC millis+Z", "[dates]") {
    // Millisecond precision + 'Z' — the one shape every Airtable column accepts
    // (the C# target live-caught that 7-digit fractional forms are rejected).
    REQUIRE(json(DateTime::from_epoch_millis(1'705'314'600'000)).get<std::string>() ==
            "2024-01-15T10:30:00.000Z");
    REQUIRE(json(DateTime::from_epoch_millis(1'705'314'600'123)).get<std::string>() ==
            "2024-01-15T10:30:00.123Z");
}

TEST_CASE("datetime round-trips through the codec", "[dates]") {
    const auto original = DateTime::from_epoch_millis(1'705'314'600'123);
    REQUIRE(json(original).get<DateTime>() == original);
}

TEST_CASE("civil math handles pre-epoch and leap days", "[dates]") {
    REQUIRE(days_from_civil(1970, 1, 1) == 0);
    REQUIRE(days_from_civil(1969, 12, 31) == -1);
    REQUIRE(decode("2024-02-29").epoch_millis() == 1'709'164'800'000); // leap day
    const auto civil = civil_from_days(days_from_civil(2024, 2, 29));
    REQUIRE(civil.year == 2024);
    REQUIRE(civil.month == 2);
    REQUIRE(civil.day == 29);
}

// ---- Duration codec (wire = numeric seconds; Java folds these into the
// special/error file, C++ keeps them beside the date codec) --------------------

TEST_CASE("duration decodes wire seconds", "[dates]") {
    REQUIRE(json(1).get<Duration>().seconds == 1.0);
    REQUIRE(json(3600).get<Duration>().seconds == 3600.0);
    REQUIRE(json(90.5).get<Duration>().seconds == 90.5);
}

TEST_CASE("duration encodes wire seconds, never a formatted string", "[dates]") {
    REQUIRE(json(Duration{90.0}) == json(90.0));
    REQUIRE(json(Duration{90.0}).is_number());
    REQUIRE(json(Duration{3600.0}).get<double>() == 3600.0);
}

// ---- runtime date coercions ------------------------------------------------------

TEST_CASE("runtime d() coerces blank, strings, epoch seconds, arrays", "[dates]") {
    REQUIRE(rt::d(json(nullptr)) == std::nullopt);
    REQUIRE(rt::d(json("2024-01-15T10:30:00Z"))->epoch_millis() == 1'705'314'600'000);
    REQUIRE(rt::d(json("junk")) == std::nullopt); // formula semantics degrade, no throw
    REQUIRE(rt::d(json(1'705'314'600))->epoch_millis() == 1'705'314'600'000);
    REQUIRE(rt::d(json::parse(R"(["2024-01-15", "2024-02-01"])"))->epoch_millis() ==
            1'705'276'800'000);
    REQUIRE(rt::d(json::array()) == std::nullopt);
}

TEST_CASE("runtime v() boxes DateTime and Duration onto the wire shapes", "[dates]") {
    REQUIRE(rt::v(DateTime::from_epoch_millis(1'705'314'600'000)) ==
            json("2024-01-15T10:30:00.000Z"));
    REQUIRE(rt::v(Duration{30.0}) == json(30.0));
}

// ---- vendored tz (SET_TIMEZONE foundation — the function itself lands in F8) -----

TEST_CASE("vendored Hinnant tz resolves zones from the OS database", "[dates][tz]") {
    const auto* zone = date::locate_zone("America/New_York");
    REQUIRE(zone != nullptr);
    // 2024-01-15 15:30 UTC == 10:30 EST (UTC-5, winter).
    const auto utc = date::sys_seconds{std::chrono::seconds{1'705'332'600}};
    const auto local = date::make_zoned(zone, utc).get_local_time();
    REQUIRE(std::chrono::duration_cast<std::chrono::seconds>(local.time_since_epoch()).count() ==
            1'705'332'600 - 5 * 3600);
    REQUIRE_THROWS(date::locate_zone("Not/AZone"));
}
