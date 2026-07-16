#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula math functions. Whole finite results are stored as
// integers (num_value), matching the boxed-node targets, so 2+3 renders "5".

namespace detail {

inline double round_half_away_from_zero(double d) {
    return d >= 0 ? std::floor(d + 0.5) : std::ceil(d - 0.5);
}

/// Box a double: whole finite magnitudes below 1e15 store as integers.
inline json num_value(double d) {
    if (std::isfinite(d) && d == std::floor(d) && std::abs(d) < 1e15) {
        return json(static_cast<int64_t>(d));
    }
    return json(d);
}

} // namespace detail

inline json SUM(const std::vector<json>& args) {
    double total = 0.0;
    for (const double n : an(args)) {
        total += n;
    }
    return detail::num_value(total);
}

inline json AVERAGE(const std::vector<json>& args) {
    const auto nums = an(args);
    if (nums.empty()) {
        return json(std::nan(""));
    }
    double total = 0.0;
    for (const double n : nums) {
        total += n;
    }
    return detail::num_value(total / static_cast<double>(nums.size()));
}

inline json MIN(const std::vector<json>& args) {
    const auto nums = an(args);
    if (nums.empty()) {
        return json(std::nan(""));
    }
    return detail::num_value(*std::min_element(nums.begin(), nums.end()));
}

inline json MAX(const std::vector<json>& args) {
    const auto nums = an(args);
    if (nums.empty()) {
        return json(std::nan(""));
    }
    return detail::num_value(*std::max_element(nums.begin(), nums.end()));
}

inline json COUNT(const std::vector<json>& args) {
    int64_t count = 0;
    for (const json& value : a(args)) {
        if (value.is_number()) {
            ++count;
        }
    }
    return json(count);
}

inline json COUNTA(const std::vector<json>& args) {
    int64_t count = 0;
    for (const json& value : a(args)) {
        if (value.is_string() && value.get_ref<const std::string&>().empty()) {
            continue;
        }
        ++count;
    }
    return json(count);
}

inline json ROUND(const json& value, const json& precision = json(nullptr)) {
    const double factor = std::pow(10.0, static_cast<int>(n(precision)));
    return detail::num_value(detail::round_half_away_from_zero(n(value) * factor) / factor);
}

inline json ROUNDUP(const json& value, const json& precision = json(nullptr)) {
    const double x = n(value);
    const double factor = std::pow(10.0, static_cast<int>(n(precision)));
    return detail::num_value(x >= 0 ? std::ceil(x * factor) / factor
                                    : std::floor(x * factor) / factor);
}

inline json ROUNDDOWN(const json& value, const json& precision = json(nullptr)) {
    const double x = n(value);
    const double factor = std::pow(10.0, static_cast<int>(n(precision)));
    return detail::num_value(x >= 0 ? std::floor(x * factor) / factor
                                    : std::ceil(x * factor) / factor);
}

inline json CEILING(const json& value, const json& significance = json(nullptr)) {
    const double s = significance.is_null() ? 1.0 : n(significance);
    const double sig = s == 0.0 ? 1.0 : s;
    return detail::num_value(std::ceil(n(value) / sig) * sig);
}

inline json FLOOR(const json& value, const json& significance = json(nullptr)) {
    const double s = significance.is_null() ? 1.0 : n(significance);
    const double sig = s == 0.0 ? 1.0 : s;
    return detail::num_value(std::floor(n(value) / sig) * sig);
}

inline json LOG(const json& value, const json& base = json(nullptr)) {
    const double x = n(value);
    if (!base.is_null()) {
        return detail::num_value(std::log(x) / std::log(n(base)));
    }
    return detail::num_value(std::log10(x));
}

inline json EVEN(const json& value) {
    const double x = n(value);
    const double c = std::ceil(std::abs(x));
    double r = std::fmod(c, 2.0) == 0.0 ? c : c + 1;
    if (x < 0) {
        r = -r;
    }
    return json(static_cast<int64_t>(r));
}

inline json ODD(const json& value) {
    const double x = n(value);
    const double c = std::ceil(std::abs(x));
    double r = std::fmod(c, 2.0) == 1.0 ? c : c + 1;
    if (x < 0) {
        r = -r;
    }
    return json(static_cast<int64_t>(r));
}

inline json VALUE(const json& value) {
    if (value.is_null()) {
        return json(int64_t{0});
    }
    const std::string text = s(value);
    try {
        size_t consumed = 0;
        if (text.find('.') != std::string::npos) {
            const double d = std::stod(text, &consumed);
            if (consumed == text.size()) {
                return json(d);
            }
        } else {
            const long long l = std::stoll(text, &consumed);
            if (consumed == text.size()) {
                return json(static_cast<int64_t>(l));
            }
        }
    } catch (const std::exception&) {
        // fall through to NaN
    }
    return json(std::nan(""));
}

inline json POWER(const json& base, const json& exp) {
    return detail::num_value(std::pow(n(base), n(exp)));
}

inline json MOD(const json& value, const json& divisor) {
    const double d = n(divisor);
    if (d == 0.0) {
        return json(std::nan(""));
    }
    return detail::num_value(std::fmod(n(value), d));
}

inline json ABS(const json& value) {
    return detail::num_value(std::abs(n(value)));
}

inline json EXP(const json& value) {
    const double x = n(value);
    // EXP(1.0) pins to the M_E constant: std::exp(1.0) can differ by one ULP
    // from the V8/Airtable Math.E (the JVM needed the same pin).
    return detail::num_value(x == 1.0 ? 2.718281828459045 : std::exp(x));
}

inline json SQRT(const json& value) {
    return detail::num_value(std::sqrt(n(value)));
}

inline json INT(const json& value) {
    return json(static_cast<int64_t>(std::floor(n(value))));
}

} // namespace myairtable::runtime
