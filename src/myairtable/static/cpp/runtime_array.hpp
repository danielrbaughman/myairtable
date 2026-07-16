#pragma once

#include <string>
#include <vector>

#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula array functions.

inline json ARRAYJOIN(const json& arr, const json& separator = json(nullptr)) {
    const std::string sep = separator.is_null() ? ", " : s(separator);
    if (arr.is_null()) {
        return json("");
    }
    if (arr.is_array()) {
        std::string out;
        bool first = true;
        for (const json& value : arr) {
            if (!first) {
                out += sep;
            }
            out += s(value);
            first = false;
        }
        return json(out);
    }
    return json(s(arr));
}

inline json ARRAYUNIQUE(const json& arr) {
    json out = json::array();
    if (arr.is_null()) {
        return out;
    }
    if (!arr.is_array()) {
        out.push_back(arr);
        return out;
    }
    for (const json& value : arr) {
        bool seen = false;
        for (const json& kept : out) {
            if (kept == value) { // deep value equality
                seen = true;
                break;
            }
        }
        if (!seen) {
            out.push_back(value);
        }
    }
    return out;
}

inline json ARRAYCOMPACT(const json& arr) {
    json out = json::array();
    if (arr.is_null()) {
        return out;
    }
    if (!arr.is_array()) {
        out.push_back(arr);
        return out;
    }
    for (const json& value : arr) {
        if (value.is_null()) {
            continue;
        }
        if (value.is_string() && value.get_ref<const std::string&>().empty()) {
            continue;
        }
        out.push_back(value);
    }
    return out;
}

namespace detail {
inline void flatten_into(const json& items, json& out) {
    for (const json& value : items) {
        if (value.is_array()) {
            flatten_into(value, out);
        } else {
            out.push_back(value);
        }
    }
}
} // namespace detail

inline json ARRAYFLATTEN(const json& arr) {
    json out = json::array();
    if (arr.is_null()) {
        return out;
    }
    if (!arr.is_array()) {
        out.push_back(arr);
        return out;
    }
    detail::flatten_into(arr, out);
    return out;
}

} // namespace myairtable::runtime
