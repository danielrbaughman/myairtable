#pragma once

#include <cmath>
#include <cstdint>
#include <string>

#include "airtable_date.hpp"
#include "airtable_json.hpp"
#include "airtable_tz.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula date functions. All UTC except SET_TIMEZONE (vendored tz)
// and TODAY (local start of day, like the other targets).

namespace detail {

struct CivilTime {
    int64_t year;
    unsigned month;
    unsigned day;
    int64_t hour;
    int64_t minute;
    int64_t second;
    int64_t days_since_epoch;
};

inline CivilTime civil_time(const DateTime& dt) {
    int64_t ms = dt.epoch_millis();
    int64_t days = ms / 86'400'000;
    int64_t rem = ms - days * 86'400'000;
    if (rem < 0) {
        rem += 86'400'000;
        --days;
    }
    const CivilDate date = civil_from_days(days);
    return CivilTime{date.year,           date.month,        date.day, rem / 3'600'000,
                     (rem / 60'000) % 60, (rem / 1000) % 60, days};
}

/// 0 = Sunday … 6 = Saturday (1970-01-01 was a Thursday).
inline int day_of_week(const DateTime& dt) {
    const auto days = civil_time(dt).days_since_epoch;
    return static_cast<int>(((days % 7) + 7 + 4) % 7);
}

inline bool is_working_day(const DateTime& dt) {
    const int dow = day_of_week(dt);
    return dow != 0 && dow != 6;
}

inline unsigned days_in_month(int64_t year, unsigned month) {
    static constexpr unsigned lengths[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (month == 2) {
        const bool leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
        return leap ? 29 : 28;
    }
    return lengths[month - 1];
}

inline DateTime add_days(const DateTime& dt, int64_t days) {
    return DateTime::from_epoch_millis(dt.epoch_millis() + days * 86'400'000);
}

/// Calendar-aware month arithmetic with end-of-month clamping (AddMonths parity).
inline DateTime add_months(const DateTime& dt, int64_t months) {
    const CivilTime c = civil_time(dt);
    int64_t linear = c.year * 12 + static_cast<int64_t>(c.month) - 1 + months;
    const int64_t year = linear >= 0 ? linear / 12 : (linear - 11) / 12;
    const auto month = static_cast<unsigned>(linear - year * 12 + 1);
    const unsigned day = std::min(c.day, days_in_month(year, month));
    const int64_t days = days_from_civil(year, month, day);
    const int64_t time_ms =
        ((c.hour * 60 + c.minute) * 60 + c.second) * 1000 + dt.epoch_millis() % 1000;
    return DateTime::from_epoch_millis(days * 86'400'000 + time_ms);
}

inline std::string pad2(int64_t v) {
    return (v < 10 ? "0" : "") + std::to_string(v);
}

inline std::string plural(int64_t n, const std::string& unit) {
    return std::to_string(n) + " " + unit + (n == 1 ? "" : "s");
}

} // namespace detail

inline json NOW() {
    return json(format_datetime(DateTime{std::chrono::system_clock::now()}));
}

inline json TODAY() {
    const DateTime now{std::chrono::system_clock::now()};
    try {
        const auto* zone = date::current_zone();
        const auto local = date::make_zoned(zone, now.tp).get_local_time();
        const auto local_days = std::chrono::time_point_cast<date::days>(local);
        const auto start_local =
            date::local_days{std::chrono::duration_cast<date::days>(local_days.time_since_epoch())};
        const auto start_sys = date::make_zoned(zone, start_local).get_sys_time();
        return json(format_datetime(DateTime{start_sys}));
    } catch (const std::exception&) {
        const int64_t days = now.epoch_millis() / 86'400'000;
        return json(format_datetime(DateTime::from_epoch_millis(days * 86'400'000)));
    }
}

inline json YEAR(const json& value) {
    const auto dt = d(value);
    return json(dt ? detail::civil_time(*dt).year : int64_t{0});
}

inline json MONTH(const json& value) {
    const auto dt = d(value);
    return json(dt ? static_cast<int64_t>(detail::civil_time(*dt).month) : int64_t{0});
}

inline json DAY(const json& value) {
    const auto dt = d(value);
    return json(dt ? static_cast<int64_t>(detail::civil_time(*dt).day) : int64_t{0});
}

inline json HOUR(const json& value) {
    const auto dt = d(value);
    return json(dt ? detail::civil_time(*dt).hour : int64_t{0});
}

inline json MINUTE(const json& value) {
    const auto dt = d(value);
    return json(dt ? detail::civil_time(*dt).minute : int64_t{0});
}

inline json SECOND(const json& value) {
    const auto dt = d(value);
    return json(dt ? detail::civil_time(*dt).second : int64_t{0});
}

inline json WEEKDAY(const json& value) {
    const auto dt = d(value);
    return json(dt ? static_cast<int64_t>(detail::day_of_week(*dt)) : int64_t{0});
}

inline json DATETIME_DIFF(const json& d1v, const json& d2v, const json& unit = json(nullptr)) {
    const auto d1 = d(d1v);
    const auto d2 = d(d2v);
    if (!d1 || !d2) {
        return json(int64_t{0});
    }
    const double diff_secs = static_cast<double>(d1->epoch_millis() - d2->epoch_millis()) / 1000.0;
    const std::string u = s(unit);
    if (u == "milliseconds") {
        return json(static_cast<int64_t>(diff_secs * 1000));
    }
    if (u == "seconds") {
        return json(static_cast<int64_t>(diff_secs));
    }
    if (u == "minutes") {
        return json(static_cast<int64_t>(diff_secs / 60));
    }
    if (u == "hours") {
        return json(static_cast<int64_t>(diff_secs / 3600));
    }
    if (u == "weeks") {
        return json(static_cast<int64_t>(diff_secs / (86400.0 * 7)));
    }
    if (u == "months") {
        const auto c1 = detail::civil_time(*d1);
        const auto c2 = detail::civil_time(*d2);
        return json((c1.year - c2.year) * 12 + (static_cast<int64_t>(c1.month) - c2.month));
    }
    if (u == "years") {
        return json(detail::civil_time(*d1).year - detail::civil_time(*d2).year);
    }
    return json(static_cast<int64_t>(diff_secs / 86400)); // "days" and unknown units
}

inline json DATEADD(const json& date_value, const json& count, const json& unit) {
    const auto dt = d(date_value);
    if (!dt) {
        return json(nullptr);
    }
    const auto amount = static_cast<int64_t>(n(count));
    const std::string u = s(unit);
    DateTime result = *dt;
    if (u == "years") {
        result = detail::add_months(result, amount * 12);
    } else if (u == "months") {
        result = detail::add_months(result, amount);
    } else if (u == "weeks") {
        result = detail::add_days(result, amount * 7);
    } else if (u == "hours") {
        result = DateTime::from_epoch_millis(result.epoch_millis() + amount * 3'600'000);
    } else if (u == "minutes") {
        result = DateTime::from_epoch_millis(result.epoch_millis() + amount * 60'000);
    } else if (u == "seconds") {
        result = DateTime::from_epoch_millis(result.epoch_millis() + amount * 1000);
    } else {
        result = detail::add_days(result, amount); // "days" and unknown units
    }
    return json(format_datetime(result));
}

inline json IS_SAME(const json& d1, const json& d2, const json& unit = json(nullptr)) {
    const json u = unit.is_null() ? json("days") : unit;
    return json(DATETIME_DIFF(d1, d2, u).get<int64_t>() == 0);
}

inline json IS_BEFORE(const json& d1, const json& d2, const json& unit = json(nullptr)) {
    const json u = unit.is_null() ? json("days") : unit;
    return json(DATETIME_DIFF(d1, d2, u).get<int64_t>() < 0);
}

inline json IS_AFTER(const json& d1, const json& d2, const json& unit = json(nullptr)) {
    const json u = unit.is_null() ? json("days") : unit;
    return json(DATETIME_DIFF(d1, d2, u).get<int64_t>() > 0);
}

namespace detail {
inline std::string human_duration(const std::optional<DateTime>& d1,
                                  const std::optional<DateTime>& d2) {
    if (!d1 || !d2) {
        return "";
    }
    const int64_t diff = std::abs((d1->epoch_millis() - d2->epoch_millis()) / 1000);
    const int64_t minutes = diff / 60;
    const int64_t hours = minutes / 60;
    const int64_t days = hours / 24;
    const auto c1 = civil_time(*d1);
    const auto c2 = civil_time(*d2);
    const int64_t months =
        std::abs((c1.year - c2.year) * 12 + (static_cast<int64_t>(c1.month) - c2.month));
    const int64_t years = months / 12;
    if (years > 0) {
        return plural(years, "year");
    }
    if (months > 0) {
        return plural(months, "month");
    }
    if (days > 0) {
        return plural(days, "day");
    }
    if (hours > 0) {
        return plural(hours, "hour");
    }
    if (minutes > 0) {
        return plural(minutes, "minute");
    }
    return plural(diff, "second");
}
} // namespace detail

inline json TONOW(const json& date_value, const json& unit = json(nullptr)) {
    if (!unit.is_null()) {
        return DATETIME_DIFF(NOW(), date_value, unit);
    }
    return json(detail::human_duration(d(date_value), d(NOW())));
}

inline json FROMNOW(const json& date_value, const json& unit = json(nullptr)) {
    if (!unit.is_null()) {
        return DATETIME_DIFF(date_value, NOW(), unit);
    }
    return json(detail::human_duration(d(date_value), d(NOW())));
}

inline json WEEKNUM(const json& date_value, const json& start_day = json(nullptr)) {
    const auto dt = d(date_value);
    if (!dt) {
        return json(int64_t{0});
    }
    std::string wanted = s(start_day);
    for (auto& ch : wanted) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    const auto c = detail::civil_time(*dt);
    const int64_t jan1_days = days_from_civil(c.year, 1, 1);
    const int dow_jan1_sunday0 = static_cast<int>(((jan1_days % 7) + 7 + 4) % 7);
    const int first = wanted == "monday"      ? 1
                      : wanted == "tuesday"   ? 2
                      : wanted == "wednesday" ? 3
                      : wanted == "thursday"  ? 4
                      : wanted == "friday"    ? 5
                      : wanted == "saturday"  ? 6
                                              : 0; // sunday / unknown
    const int dow_jan1 = ((dow_jan1_sunday0 - first) % 7 + 7) % 7;
    const int64_t day_of_year = c.days_since_epoch - jan1_days + 1;
    const int64_t week = (day_of_year + dow_jan1 - 1) / 7 + 1;
    return json(week);
}

inline json WORKDAY(const json& start, const json& num_days) {
    const auto dt = d(start);
    if (!dt) {
        return json(nullptr);
    }
    DateTime current = *dt;
    int remaining = static_cast<int>(n(num_days));
    const int direction = remaining >= 0 ? 1 : -1;
    remaining = std::abs(remaining);
    while (remaining > 0) {
        current = detail::add_days(current, direction);
        if (detail::is_working_day(current)) {
            --remaining;
        }
    }
    return json(format_datetime(current));
}

inline json WORKDAY_DIFF(const json& start, const json& end) {
    const auto d1 = d(start);
    const auto d2 = d(end);
    if (!d1 || !d2) {
        return json(int64_t{0});
    }
    int64_t count = 0;
    DateTime current = *d1;
    const int direction = d2->epoch_millis() > d1->epoch_millis() ? 1 : -1;
    if (detail::is_working_day(current)) {
        count += direction;
    }
    while ((direction == 1 && current.epoch_millis() < d2->epoch_millis()) ||
           (direction == -1 && current.epoch_millis() > d2->epoch_millis())) {
        current = detail::add_days(current, direction);
        if (detail::is_working_day(current)) {
            count += direction;
        }
    }
    return json(count);
}

inline json SET_TIMEZONE(const json& date_value, const json& tz) {
    const auto dt = d(date_value);
    if (!dt) {
        return json(nullptr);
    }
    try {
        const auto* zone = date::locate_zone(s(tz));
        const auto info =
            zone->get_info(std::chrono::time_point_cast<std::chrono::seconds>(dt->tp));
        const auto offset_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(info.offset).count();
        return json(format_datetime(DateTime::from_epoch_millis(dt->epoch_millis() + offset_ms)));
    } catch (const std::exception&) {
        return json(format_datetime(*dt)); // unknown zone: unshifted (C# parity)
    }
}

inline json DATETIME_FORMAT(const json& date_value, const json& fmt = json(nullptr)) {
    const auto dt = d(date_value);
    if (!dt) {
        return json("");
    }
    if (fmt.is_null()) {
        return json(format_datetime(*dt));
    }
    // Moment-style token subset: YYYY YY MM M DD D HH H mm m ss s.
    const auto c = detail::civil_time(*dt);
    const std::string pattern = s(fmt);
    std::string out;
    size_t i = 0;
    const auto starts = [&](const char* token) {
        return pattern.compare(i, std::string::traits_type::length(token), token) == 0;
    };
    while (i < pattern.size()) {
        if (starts("YYYY")) {
            out += std::to_string(c.year);
            i += 4;
        } else if (starts("YY")) {
            out += detail::pad2(((c.year % 100) + 100) % 100);
            i += 2;
        } else if (starts("MM")) {
            out += detail::pad2(c.month);
            i += 2;
        } else if (starts("DD")) {
            out += detail::pad2(c.day);
            i += 2;
        } else if (starts("HH")) {
            out += detail::pad2(c.hour);
            i += 2;
        } else if (starts("mm")) {
            out += detail::pad2(c.minute);
            i += 2;
        } else if (starts("ss")) {
            out += detail::pad2(c.second);
            i += 2;
        } else if (starts("M")) {
            out += std::to_string(c.month);
            i += 1;
        } else if (starts("D")) {
            out += std::to_string(c.day);
            i += 1;
        } else if (starts("H")) {
            out += std::to_string(c.hour);
            i += 1;
        } else if (starts("m")) {
            out += std::to_string(c.minute);
            i += 1;
        } else if (starts("s")) {
            out += std::to_string(c.second);
            i += 1;
        } else {
            out.push_back(pattern[i]);
            i += 1;
        }
    }
    return json(out);
}

inline json DATESTR(const json& value) {
    const auto dt = d(value);
    if (!dt) {
        return json("");
    }
    const auto c = detail::civil_time(*dt);
    return json(std::to_string(c.year) + "-" + detail::pad2(c.month) + "-" + detail::pad2(c.day));
}

inline json TIMESTR(const json& value) {
    const auto dt = d(value);
    if (!dt) {
        return json("");
    }
    const auto c = detail::civil_time(*dt);
    return json(detail::pad2(c.hour) + ":" + detail::pad2(c.minute) + ":" + detail::pad2(c.second));
}

inline json DATETIME_PARSE(const json& value, const json& /*fmt*/ = json(nullptr)) {
    const auto dt = d(value);
    return dt ? json(format_datetime(*dt)) : json(nullptr);
}

} // namespace myairtable::runtime
