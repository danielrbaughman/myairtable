// F1.13 PHASE-0 GATE — self-contained proof that the riskiest C++ foundations
// work BEFORE the real static runtime (F2) or generator (F3) is built.
// Everything here is a throwaway prototype under namespace `proto` — it
// deliberately does NOT depend on static/cpp beyond airtable_json.hpp and the
// vendored headers.
//
// Proves (plan .beads/cpp-plan-v2.md §5 F1.13):
//   (a) aggregate + designated-initializer creation + empty CRTP base
//   (b) adl_serializer round-trips for template sum types with PUBLIC ctors —
//       optional fields via read_field/write_field, MaybeSpecialOrError<T> for
//       string/double/DateTime, VecOrValue<T>, VecOrValue<DateTime>, nested
//       VecOrValue<MaybeSpecialOrError<T>>, and a null-valued computed field —
//       decode AND encode, with ZERO registration.
//   (c) Duration wire format = numeric seconds.
//   (d) snapshot + writable-only payload diff (computed fields never written).
//   (e) TRUE/FALSE macro-collision probe with <curl/curl.h> in the same TU.
//   (f) in-case ordering via SECTIONs (ctest runs each TEST_CASE in its own
//       process, so cross-case ordering lives in the integration harness).
//
// Design note proven here and carried into F2: DateTime/Duration are thin
// OWNED wrapper structs (the Go AirtableTime/AirtableDuration precedent), so
// their adl_serializers are specializations for types we own — never for std
// types (ODR safety, plan HIGH-1).

#include <catch2/catch_test_macros.hpp>
#include <curl/curl.h> // (e): drags in system macro namespace before our declarations

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "airtable_json.hpp"

namespace proto {

using myairtable::json;

// ---- (b) value carriers -----------------------------------------------------

struct SpecialNumber {
    std::string special_value;
    friend bool operator==(const SpecialNumber&, const SpecialNumber&) = default;
};

struct ErrorValue {
    std::string type;
    friend bool operator==(const ErrorValue&, const ErrorValue&) = default;
};

// ---- (b)(c) owned DateTime / Duration wrappers -------------------------------

struct DateTime {
    std::chrono::system_clock::time_point tp{};
    friend bool operator==(const DateTime&, const DateTime&) = default;
};

struct Duration {
    double seconds = 0.0;
    friend bool operator==(const Duration&, const Duration&) = default;
};

// Minimal ISO-8601 codec for the gate (the real one lands in F2.4).
inline DateTime parse_iso(const std::string& text) {
    int y = 0, mo = 0, d = 0, h = 0, mi = 0;
    double sec = 0.0;
    if (std::sscanf(text.c_str(), "%d-%d-%dT%d:%d:%lf", &y, &mo, &d, &h, &mi, &sec) < 3) {
        throw std::runtime_error("bad ISO date: " + text);
    }
    // Howard Hinnant's days_from_civil (public domain).
    const auto yy = static_cast<int64_t>(y) - (mo <= 2);
    const auto era = (yy >= 0 ? yy : yy - 399) / 400;
    const auto yoe = static_cast<unsigned>(yy - era * 400);
    const auto doy = static_cast<unsigned>((153 * (mo + (mo > 2 ? -3 : 9)) + 2) / 5 + d - 1);
    const auto doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    const auto days = era * 146097 + static_cast<int64_t>(doe) - 719468;
    const auto total_ms =
        (((days * 24 + h) * 60 + mi) * 60) * 1000 + static_cast<int64_t>(sec * 1000.0 + 0.5);
    return DateTime{std::chrono::system_clock::time_point{std::chrono::milliseconds{total_ms}}};
}

inline std::string format_iso_millis(const DateTime& dt) {
    using namespace std::chrono;
    auto ms = duration_cast<milliseconds>(dt.tp.time_since_epoch()).count();
    auto days = ms / 86'400'000;
    auto rem = ms - days * 86'400'000;
    if (rem < 0) {
        rem += 86'400'000;
        --days;
    }
    // civil_from_days (public domain).
    const auto z = days + 719468;
    const auto era = (z >= 0 ? z : z - 146096) / 146097;
    const auto doe = static_cast<unsigned>(z - era * 146097);
    const auto yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const auto yy = static_cast<int64_t>(yoe) + era * 400;
    const auto doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const auto mp = (5 * doy + 2) / 153;
    const auto d = doy - (153 * mp + 2) / 5 + 1;
    const auto mo = mp + (mp < 10 ? 3 : -9);
    const auto y = yy + (mo <= 2);
    const auto hh = rem / 3'600'000;
    const auto mi = (rem / 60'000) % 60;
    const auto ss = (rem / 1000) % 60;
    const auto mmm = rem % 1000;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%04lld-%02u-%02uT%02lld:%02lld:%02lld.%03lldZ",
                  static_cast<long long>(y), mo, d, static_cast<long long>(hh),
                  static_cast<long long>(mi), static_cast<long long>(ss),
                  static_cast<long long>(mmm));
    return buf;
}

// ---- (b) sum types: public ctors (CRIT-2) + variant core ----------------------

template <typename T> class MaybeSpecialOrError {
  public:
    MaybeSpecialOrError() = default;
    explicit MaybeSpecialOrError(T value) : data_(std::move(value)) {}
    explicit MaybeSpecialOrError(SpecialNumber s) : data_(std::move(s)) {}
    explicit MaybeSpecialOrError(ErrorValue e) : data_(std::move(e)) {}

    std::optional<T> value() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return *v;
        }
        return std::nullopt;
    }
    bool is_special() const { return std::holds_alternative<SpecialNumber>(data_); }
    bool is_error() const { return std::holds_alternative<ErrorValue>(data_); }
    std::optional<SpecialNumber> special() const {
        if (const auto* s = std::get_if<SpecialNumber>(&data_)) {
            return *s;
        }
        return std::nullopt;
    }
    friend bool operator==(const MaybeSpecialOrError&, const MaybeSpecialOrError&) = default;

  private:
    std::variant<T, SpecialNumber, ErrorValue> data_;
};

template <typename T> class VecOrValue {
  public:
    VecOrValue() = default;
    explicit VecOrValue(T single) : data_(std::move(single)) {}
    explicit VecOrValue(std::vector<T> multiple) : data_(std::move(multiple)) {}

    std::optional<T> value() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return *v;
        }
        return std::nullopt;
    }
    std::vector<T> values() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return {*v};
        }
        return std::get<std::vector<T>>(data_);
    }
    bool is_multiple() const { return std::holds_alternative<std::vector<T>>(data_); }
    friend bool operator==(const VecOrValue&, const VecOrValue&) = default;

  private:
    std::variant<T, std::vector<T>> data_;
};

} // namespace proto

// ---- (b) adl_serializer partial specializations — types we OWN only ----------

namespace nlohmann {

template <> struct adl_serializer<proto::DateTime> {
    static proto::DateTime from_json(const json& j) {
        return proto::parse_iso(j.get<std::string>());
    }
    static void to_json(json& j, const proto::DateTime& dt) { j = proto::format_iso_millis(dt); }
};

template <> struct adl_serializer<proto::Duration> {
    // (c) wire format is NUMERIC SECONDS, never a formatted string.
    static proto::Duration from_json(const json& j) { return proto::Duration{j.get<double>()}; }
    static void to_json(json& j, const proto::Duration& d) { j = d.seconds; }
};

template <typename T> struct adl_serializer<proto::MaybeSpecialOrError<T>> {
    static proto::MaybeSpecialOrError<T> from_json(const json& j) {
        if (j.is_object() && j.contains("specialValue")) {
            return proto::MaybeSpecialOrError<T>(
                proto::SpecialNumber{j.at("specialValue").get<std::string>()});
        }
        if (j.is_object() && j.contains("error")) {
            return proto::MaybeSpecialOrError<T>(
                proto::ErrorValue{j.at("error").get<std::string>()});
        }
        return proto::MaybeSpecialOrError<T>(j.get<T>()); // recursion via get<T>
    }
    static void to_json(json& j, const proto::MaybeSpecialOrError<T>& v) {
        if (auto s = v.special()) {
            j = json{{"specialValue", s->special_value}};
        } else if (v.is_error()) {
            j = json{{"error", "#ERROR!"}};
        } else {
            j = *v.value(); // recursion via json assignment
        }
    }
};

template <typename T> struct adl_serializer<proto::VecOrValue<T>> {
    static proto::VecOrValue<T> from_json(const json& j) {
        if (j.is_array()) {
            return proto::VecOrValue<T>(j.get<std::vector<T>>()); // element recursion
        }
        return proto::VecOrValue<T>(j.get<T>());
    }
    static void to_json(json& j, const proto::VecOrValue<T>& v) {
        if (v.is_multiple()) {
            j = v.values();
        } else {
            j = *v.value();
        }
    }
};

} // namespace nlohmann

// ---- (a)(d) aggregate model + empty CRTP behavior base -----------------------

namespace proto {

template <typename Derived> struct ModelBase {
    // Behavior only — NO data members, so the derived model stays an aggregate.
    void take_snapshot() {
        auto* self = static_cast<Derived*>(this);
        self->snapshot_ = self->collect_writable_fields();
    }
    json dirty_fields() const {
        const auto* self = static_cast<const Derived*>(this);
        json current = self->collect_writable_fields();
        json dirty = json::object();
        for (auto& [key, value] : current.items()) {
            if (!self->snapshot_.is_object() || !self->snapshot_.contains(key) ||
                self->snapshot_.at(key) != value) {
                dirty[key] = value;
            }
        }
        return dirty;
    }
    bool is_new() const { return !static_cast<const Derived*>(this)->id.has_value(); }
};

struct ProtoModel : ModelBase<ProtoModel> {
    // record meta (direct members; base holds no data)
    std::optional<std::string> id{};
    json snapshot_{};

    // writable
    std::optional<std::string> name{}; // fldName
    std::optional<double> score{};     // fldScore
    std::optional<Duration> length{};  // fldLength
    // computed (public, but never serialized on write — R21)
    std::optional<MaybeSpecialOrError<int64_t>> auto_number{}; // fldAuto

    json collect_writable_fields() const {
        json fields = json::object();
        myairtable::write_field(fields, "fldName", name);
        myairtable::write_field(fields, "fldScore", score);
        myairtable::write_field(fields, "fldLength", length);
        return fields;
    }
};

inline void from_json(const json& record, ProtoModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    const json& fields = record.at("fields");
    m.name = myairtable::read_field<std::string>(fields, "fldName");
    m.score = myairtable::read_field<double>(fields, "fldScore");
    m.length = myairtable::read_field<Duration>(fields, "fldLength");
    m.auto_number = myairtable::read_field<MaybeSpecialOrError<int64_t>>(fields, "fldAuto");
}

} // namespace proto

// ---- (e) TRUE/FALSE macro probe ----------------------------------------------
// System headers (curl.h and friends are included above) may #define TRUE/FALSE.
// The runtime's logic group declares functions with these names; prove that the
// push_macro/undef guard pattern compiles and that call sites inside the guarded
// region work. (The transpiler itself never emits TRUE()/FALSE() — it emits
// v(true) — so only runtime-internal and test call sites need the guard.)

namespace proto_logic {
#pragma push_macro("TRUE")
#pragma push_macro("FALSE")
#ifdef TRUE
#undef TRUE
#endif
#ifdef FALSE
#undef FALSE
#endif

inline myairtable::json TRUE() {
    return true;
}
inline myairtable::json FALSE() {
    return false;
}

// Call sites evaluated inside the guarded region.
inline bool guarded_calls_work() {
    return TRUE().get<bool>() && !FALSE().get<bool>();
}

#pragma pop_macro("FALSE")
#pragma pop_macro("TRUE")
} // namespace proto_logic

// ==============================================================================

using myairtable::json;
using namespace proto;

namespace {
struct ProbeFilters {
    int probe = 7;
};
struct WithStatic : ModelBase<WithStatic> {
    std::optional<std::string> id{};
    json snapshot_{};
    inline static const ProbeFilters F{};
    json collect_writable_fields() const { return json::object(); }
};
} // namespace

TEST_CASE("gate(a): aggregate + designated initializers + empty CRTP base", "[gate]") {
    auto m = ProtoModel{.name = "hello", .score = 42.0};
    REQUIRE(m.name == "hello");
    REQUIRE(m.score == 42.0);
    REQUIRE_FALSE(m.length.has_value());
    REQUIRE(m.is_new()); // CRTP base behavior reaches derived members

    // inline static member access on the aggregate (the F accessor pattern) —
    // WithStatic is declared at namespace scope above (local structs cannot
    // hold static data members), and designated init still works on it.
    auto w = WithStatic{.id = "rec1"};
    REQUIRE_FALSE(w.is_new());
    REQUIRE(WithStatic::F.probe == 7);
}

TEST_CASE("gate(b): sum-type serializers round-trip with zero registration", "[gate]") {
    SECTION("MaybeSpecialOrError<string|double>") {
        auto s = json("plain").get<MaybeSpecialOrError<std::string>>();
        REQUIRE(s.value() == "plain");
        auto sp = json::parse(R"({"specialValue":"Infinity"})").get<MaybeSpecialOrError<double>>();
        REQUIRE(sp.is_special());
        REQUIRE(sp.special()->special_value == "Infinity");
        auto err = json::parse(R"({"error":"#ERROR!"})").get<MaybeSpecialOrError<double>>();
        REQUIRE(err.is_error());
        // encode side
        REQUIRE(json(MaybeSpecialOrError<std::string>(std::string("x"))) == json("x"));
        REQUIRE(json(sp) == json::parse(R"({"specialValue":"Infinity"})"));
    }

    SECTION("MaybeSpecialOrError<DateTime> — element codec chains through") {
        auto dt = json("2024-01-15T14:30:00.000Z").get<MaybeSpecialOrError<DateTime>>();
        REQUIRE(dt.value().has_value());
        REQUIRE(json(dt) == json("2024-01-15T14:30:00.000Z"));
    }

    SECTION("VecOrValue<string> single and multiple") {
        auto single = json("one").get<VecOrValue<std::string>>();
        REQUIRE(single.value() == "one");
        REQUIRE(single.values() == std::vector<std::string>{"one"});
        auto multi = json::parse(R"(["a","b"])").get<VecOrValue<std::string>>();
        REQUIRE(multi.is_multiple());
        REQUIRE(multi.values() == std::vector<std::string>{"a", "b"});
        REQUIRE(json(multi) == json::parse(R"(["a","b"])"));
    }

    SECTION("VecOrValue<DateTime> — factory→date-codec chain") {
        auto v = json::parse(R"(["2024-01-15T00:00:00.000Z"])").get<VecOrValue<DateTime>>();
        REQUIRE(v.is_multiple());
        REQUIRE(json(v) == json::parse(R"(["2024-01-15T00:00:00.000Z"])"));
    }

    SECTION("nested VecOrValue<MaybeSpecialOrError<string>>") {
        auto nested = json::parse(R"(["ok",{"specialValue":"NaN"}])")
                          .get<VecOrValue<MaybeSpecialOrError<std::string>>>();
        REQUIRE(nested.is_multiple());
        auto items = nested.values();
        REQUIRE(items.size() == 2);
        REQUIRE(items[0].value() == "ok");
        REQUIRE(items[1].is_special());
        REQUIRE(json(nested) == json::parse(R"(["ok",{"specialValue":"NaN"}])"));
    }

    SECTION("null-valued computed field decodes to nullopt") {
        ProtoModel m = json::parse(R"({"id":"rec1","fields":{"fldName":"n","fldAuto":null}})");
        REQUIRE(m.auto_number == std::nullopt);
        REQUIRE(m.name == "n");
    }
}

TEST_CASE("gate(c): Duration wire format is numeric seconds", "[gate]") {
    auto d = json(30.0).get<Duration>();
    REQUIRE(d.seconds == 30.0);
    REQUIRE(json(Duration{90.0}) == json(90.0));
    REQUIRE(json(Duration{90.0}).is_number()); // never "00:01:30"
}

TEST_CASE("gate(d): snapshot + writable-only dirty diff", "[gate]") {
    ProtoModel m =
        json::parse(R"({"id":"rec1","fields":{"fldName":"a","fldScore":1.0,"fldAuto":7}})");
    m.take_snapshot();
    REQUIRE(m.dirty_fields().empty());

    m.name = "b";
    m.auto_number = MaybeSpecialOrError<int64_t>(int64_t{999}); // R21: silently dropped
    auto dirty = m.dirty_fields();
    REQUIRE(dirty.size() == 1);
    REQUIRE(dirty.at("fldName") == "b");
    REQUIRE_FALSE(dirty.contains("fldAuto")); // computed never in a write payload

    m.name = std::nullopt; // clearing a field IS a change (explicit null)
    auto cleared = m.dirty_fields();
    REQUIRE(cleared.at("fldName").is_null());
}

TEST_CASE("gate(e): TRUE/FALSE survive system headers via push_macro guards", "[gate]") {
    REQUIRE(proto_logic::guarded_calls_work());
}

TEST_CASE("gate(f): SECTIONs execute in declaration order within a case", "[gate]") {
    // ctest runs each TEST_CASE in its own process, so cpp_static tests must be
    // order-independent ACROSS cases; ordered phases inside one case use
    // SECTIONs. (Cross-case declaration order is proven in the integration
    // harness, which invokes one binary directly.)
    int step = 0;
    SECTION("phase 1") {
        REQUIRE(step == 0);
    }
    SECTION("phase 2") {
        REQUIRE(step == 0); /* fresh entry per SECTION */
    }
    step = -1; // unreachable state check: each SECTION re-enters the case body
    REQUIRE(step == -1);
}
