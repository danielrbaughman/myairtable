#pragma once

#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// A computed-field error value (e.g. `{"error": "#ERROR!"}`).
struct ErrorValue {
    std::string error;

    friend bool operator==(const ErrorValue&, const ErrorValue&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::ErrorValue> {
    static myairtable::ErrorValue from_json(const json& j) {
        return myairtable::ErrorValue{j.at("error").get<std::string>()};
    }
    static void to_json(json& j, const myairtable::ErrorValue& e) { j = json{{"error", e.error}}; }
};

} // namespace nlohmann
