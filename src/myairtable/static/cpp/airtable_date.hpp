#pragma once

#include <chrono>
#include <cmath>
#include <compare>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <string>

#include "airtable_exception.hpp"
#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable {

// ---- civil-date math (Howard Hinnant's public-domain algorithms) --------------

/// Days since 1970-01-01 for a civil y/m/d.
inline int64_t days_from_civil(int64_t y, unsigned m, unsigned d) {
    y -= m <= 2;
    const int64_t era = (y >= 0 ? y : y - 399) / 400;
    const auto yoe = static_cast<unsigned>(y - era * 400);
    const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + static_cast<int64_t>(doe) - 719468;
}

struct CivilDate {
    int64_t year;
    unsigned month;
    unsigned day;
};

/// Civil y/m/d for days since 1970-01-01.
inline CivilDate civil_from_days(int64_t z) {
    z += 719468;
    const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
    const auto doe = static_cast<unsigned>(z - era * 146097);
    const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const int64_t y = static_cast<int64_t>(yoe) + era * 400;
    const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const unsigned mp = (5 * doy + 2) / 153;
    const unsigned d = doy - (153 * mp + 2) / 5 + 1;
    const unsigned m = mp + (mp < 10 ? 3 : -9);
    return CivilDate{y + (m <= 2), m, d};
}

// ---- owned DateTime wrapper ------------------------------------------------------

/// An absolute UTC timestamp — a thin OWNED wrapper over
/// `std::chrono::system_clock::time_point` (the Go AirtableTime precedent), so
/// its adl_serializer specializes a type we own, never a std type (ODR safety).
struct DateTime {
    std::chrono::system_clock::time_point tp{};

    static DateTime from_epoch_millis(int64_t ms) {
        return DateTime{std::chrono::system_clock::time_point{std::chrono::milliseconds{ms}}};
    }
    static DateTime from_epoch_seconds(double seconds) {
        return from_epoch_millis(static_cast<int64_t>(std::llround(seconds * 1000.0)));
    }

    int64_t epoch_millis() const {
        return std::chrono::duration_cast<std::chrono::milliseconds>(tp.time_since_epoch()).count();
    }
    double epoch_seconds() const { return static_cast<double>(epoch_millis()) / 1000.0; }

    friend bool operator==(const DateTime&, const DateTime&) = default;
    friend auto operator<=>(const DateTime&, const DateTime&) = default;
};

/// A duration — thin owned wrapper; wire format is NUMERIC SECONDS.
struct Duration {
    double seconds = 0.0;

    std::chrono::duration<double> chrono() const { return std::chrono::duration<double>{seconds}; }

    friend bool operator==(const Duration&, const Duration&) = default;
    friend auto operator<=>(const Duration&, const Duration&) = default;
};

// ---- ISO-8601 codec -----------------------------------------------------------------

/// Parse the three Airtable wire shapes — fractional ISO 8601, plain ISO 8601
/// (bare, 'Z', or ±hh:mm offset), and date-only "YYYY-MM-DD" (UTC midnight).
/// Returns nullopt for anything else (the AirtableDateParser analog).
inline std::optional<DateTime> try_parse_datetime(const std::string& text) {
    int y = 0, mo = 0, d = 0;
    int pos = 0;
    if (std::sscanf(text.c_str(), "%4d-%2d-%2d%n", &y, &mo, &d, &pos) < 3 || pos != 10) {
        return std::nullopt;
    }
    if (mo < 1 || mo > 12 || d < 1 || d > 31) {
        return std::nullopt;
    }

    int h = 0, mi = 0;
    double sec = 0.0;
    int offset_minutes = 0;

    if (static_cast<size_t>(pos) < text.size()) {
        if (text[pos] != 'T' && text[pos] != ' ') {
            return std::nullopt;
        }
        int tlen = 0;
        if (std::sscanf(text.c_str() + pos + 1, "%2d:%2d%n", &h, &mi, &tlen) < 2 || tlen != 5) {
            return std::nullopt;
        }
        pos += 1 + tlen;
        if (static_cast<size_t>(pos) < text.size() && text[pos] == ':') {
            int slen = 0;
            if (std::sscanf(text.c_str() + pos + 1, "%lf%n", &sec, &slen) < 1) {
                return std::nullopt;
            }
            pos += 1 + slen;
        }
        const std::string rest = text.substr(pos);
        if (rest.empty() || rest == "Z") {
            // UTC
        } else if (rest.size() == 6 && (rest[0] == '+' || rest[0] == '-') && rest[3] == ':') {
            int oh = 0, om = 0;
            if (std::sscanf(rest.c_str() + 1, "%2d:%2d", &oh, &om) != 2) {
                return std::nullopt;
            }
            offset_minutes = (rest[0] == '-' ? -1 : 1) * (oh * 60 + om);
        } else {
            return std::nullopt;
        }
        if (h > 23 || mi > 59 || sec < 0.0 || sec >= 61.0) {
            return std::nullopt;
        }
    }

    const int64_t days = days_from_civil(y, static_cast<unsigned>(mo), static_cast<unsigned>(d));
    const int64_t base_ms =
        ((days * 24 + h) * 60 + mi) * 60'000 + static_cast<int64_t>(std::llround(sec * 1000.0));
    return DateTime::from_epoch_millis(base_ms - static_cast<int64_t>(offset_minutes) * 60'000);
}

/// Encode as ISO-8601 UTC with milliseconds + 'Z' — the one write shape every
/// Airtable column type accepts (higher precision is rejected by date columns).
inline std::string format_datetime(const DateTime& dt) {
    int64_t ms = dt.epoch_millis();
    int64_t days = ms / 86'400'000;
    int64_t rem = ms - days * 86'400'000;
    if (rem < 0) {
        rem += 86'400'000;
        --days;
    }
    const CivilDate civil = civil_from_days(days);
    char buf[40];
    std::snprintf(buf, sizeof(buf), "%04lld-%02u-%02uT%02lld:%02lld:%02lld.%03lldZ",
                  static_cast<long long>(civil.year), civil.month, civil.day,
                  static_cast<long long>(rem / 3'600'000),
                  static_cast<long long>((rem / 60'000) % 60),
                  static_cast<long long>((rem / 1000) % 60), static_cast<long long>(rem % 1000));
    return buf;
}

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::DateTime> {
    static myairtable::DateTime from_json(const json& j) {
        const auto text = j.get<std::string>();
        if (auto parsed = myairtable::try_parse_datetime(text)) {
            return *parsed;
        }
        throw myairtable::DecodingError("unparseable datetime: " + text);
    }
    static void to_json(json& j, const myairtable::DateTime& dt) {
        j = myairtable::format_datetime(dt);
    }
};

template <> struct adl_serializer<myairtable::Duration> {
    static myairtable::Duration from_json(const json& j) {
        return myairtable::Duration{j.get<double>()}; // wire = numeric seconds
    }
    static void to_json(json& j, const myairtable::Duration& d) { j = d.seconds; }
};

} // namespace nlohmann

namespace myairtable::runtime {

// Date-aware coercions (reopened namespace — the runtime core is date-agnostic).

inline json v(const DateTime& value) {
    return json(value);
} // ISO millis+Z string
inline json v(const Duration& value) {
    return json(value);
} // numeric seconds

/// Coerce to a date (BLANK = nullopt); numbers are epoch seconds; unparseable
/// strings are nullopt (formula semantics degrade, they don't throw).
inline std::optional<DateTime> d(const json& value) {
    if (value.is_null()) {
        return std::nullopt;
    }
    if (value.is_string()) {
        return try_parse_datetime(value.get_ref<const std::string&>());
    }
    if (value.is_number()) {
        return DateTime::from_epoch_seconds(value.get<double>());
    }
    if (value.is_array()) {
        return value.empty() ? std::nullopt : d(value.front());
    }
    return std::nullopt;
}

} // namespace myairtable::runtime
