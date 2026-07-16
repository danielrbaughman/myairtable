#pragma once

#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// A computed-field special value (e.g. `{"specialValue": "NaN"}` / "Infinity").
struct SpecialNumber {
    std::string special_value;

    friend bool operator==(const SpecialNumber&, const SpecialNumber&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::SpecialNumber> {
    static myairtable::SpecialNumber from_json(const json& j) {
        // Strict object form only — an array here means a lookup leaked through.
        return myairtable::SpecialNumber{j.at("specialValue").get<std::string>()};
    }
    static void to_json(json& j, const myairtable::SpecialNumber& s) {
        j = json{{"specialValue", s.special_value}};
    }
};

} // namespace nlohmann
