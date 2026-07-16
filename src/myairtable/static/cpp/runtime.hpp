#pragma once

#include <cmath>
#include <cstdint>
#include <format>
#include <optional>
#include <string>
#include <vector>

#include "airtable_json.hpp"

namespace myairtable::runtime {

// Runtime support for transpiled Airtable formulas: the value coercions
// (v/n/s/a/an/as/is_truthy/is_equal/is_blank) operating on the type-erased
// value-semantic `json`. JSON null is BLANK in every coercion. The ~90 formula
// functions are added by F8 across runtime_{logic,math,string,date,array,
// regex}.hpp — namespaces reopen, the C# partial-class analog. Date/duration
// overloads (v(DateTime), d()) live beside the date codec in airtable_date.hpp.

// ---- v(): box any value into a json (formula literals / field refs) ----------

inline json v(std::nullptr_t) {
    return json(nullptr);
}
inline json v(json value) {
    return value;
} // passthrough — never re-serialize
inline json v(bool value) {
    return json(value);
}
inline json v(int value) {
    return json(value);
}
inline json v(int64_t value) {
    return json(value);
}
inline json v(double value) {
    return json(value);
}
inline json v(const char* value) {
    return value == nullptr ? json(nullptr) : json(value);
}
inline json v(const std::string& value) {
    return json(value);
}

template <typename T> json v(const std::optional<T>& value) {
    return value.has_value() ? v(*value) : json(nullptr);
}

template <typename T> json v(const std::vector<T>& values) {
    return json(values);
}

/// Generic fallback: anything with an adl_serializer (value carriers, sum types).
template <typename T> json v(const T& value) {
    return json(value);
}

// ---- scalar coercions ----------------------------------------------------------

inline bool is_blank(const json& value) {
    return value.is_null();
}

/// Coerce to a number (BLANK = 0); arrays coerce their first element.
inline double n(const json& value) {
    if (value.is_null()) {
        return 0.0;
    }
    if (value.is_number()) {
        return value.get<double>();
    }
    if (value.is_string()) {
        const auto& text = value.get_ref<const std::string&>();
        // Trim, then parse the full remainder as a double; anything else is 0.
        const auto begin = text.find_first_not_of(" \t\r\n");
        if (begin == std::string::npos) {
            return 0.0;
        }
        const auto end = text.find_last_not_of(" \t\r\n");
        const std::string trimmed = text.substr(begin, end - begin + 1);
        try {
            size_t consumed = 0;
            const double parsed = std::stod(trimmed, &consumed);
            return consumed == trimmed.size() ? parsed : 0.0;
        } catch (const std::exception&) {
            return 0.0;
        }
    }
    if (value.is_boolean()) {
        return value.get<bool>() ? 1.0 : 0.0;
    }
    if (value.is_array()) {
        return value.empty() ? 0.0 : n(value.front());
    }
    return 0.0;
}

/// Render a double the way Airtable does: whole numbers without a decimal
/// point, everything else shortest-round-trip (std::format).
inline std::string number_to_string(double value) {
    if (std::isfinite(value) && value == std::floor(value) && std::abs(value) < 1e15) {
        return std::to_string(static_cast<long long>(value));
    }
    return std::format("{}", value);
}

/// Coerce to a string (BLANK = ""); multi-value fields join with ", ".
inline std::string s(const json& value) {
    if (value.is_null()) {
        return "";
    }
    if (value.is_string()) {
        return value.get<std::string>();
    }
    if (value.is_boolean()) {
        return value.get<bool>() ? "1" : "0";
    }
    if (value.is_number()) {
        return number_to_string(value.get<double>());
    }
    if (value.is_array()) {
        // Airtable coerces a multi-value field (multi-select, multi-lookup) to a
        // string by joining its elements with ", " — not by taking the first.
        std::string out;
        bool first = true;
        for (const auto& item : value) {
            if (!first) {
                out += ", ";
            }
            out += s(item);
            first = false;
        }
        return out;
    }
    return "";
}

// ---- variadic-arg helpers ---------------------------------------------------------

/// Flatten args (one level): array args are spread, nulls dropped.
inline std::vector<json> a(const std::vector<json>& args) {
    std::vector<json> result;
    for (const auto& arg : args) {
        if (arg.is_null()) {
            continue;
        }
        if (arg.is_array()) {
            for (const auto& item : arg) {
                result.push_back(item);
            }
        } else {
            result.push_back(arg);
        }
    }
    return result;
}

inline std::vector<double> an(const std::vector<json>& args) {
    std::vector<double> result;
    for (const auto& item : a(args)) {
        result.push_back(n(item));
    }
    return result;
}

inline std::vector<std::string> as(const std::vector<json>& args) {
    std::vector<std::string> result;
    for (const auto& item : a(args)) {
        result.push_back(s(item));
    }
    return result;
}

// ---- truthiness & equality ----------------------------------------------------------

/// Airtable truthiness: BLANK/empty/0/NaN/false are falsy.
inline bool is_truthy(const json& value) {
    if (value.is_null()) {
        return false;
    }
    if (value.is_string()) {
        return !value.get_ref<const std::string&>().empty();
    }
    if (value.is_boolean()) {
        return value.get<bool>();
    }
    if (value.is_number()) {
        const double d = value.get<double>();
        return d != 0.0 && !std::isnan(d);
    }
    if (value.is_array() || value.is_object()) {
        return !value.empty();
    }
    return false;
}

/// Value equality for transpiled `=`/`!=`: numbers compared numerically,
/// everything else by string coercion (Airtable semantics). nlohmann `==` is
/// already deep value equality, but the coercions make "5" == 5 and true == 1
/// behave the way Airtable does.
inline bool is_equal(const json& a, const json& b) {
    if (a.is_null() && b.is_null()) {
        return true;
    }
    if (a.is_null() || b.is_null()) {
        return false;
    }
    if (a.is_number() && b.is_number()) {
        return n(a) == n(b);
    }
    return s(a) == s(b);
}

} // namespace myairtable::runtime
