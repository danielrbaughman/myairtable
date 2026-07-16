#pragma once

#include <optional>
#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// An Airtable button field value (read-only on the wire).
struct AirtableButton {
    std::optional<std::string> label{};
    std::optional<std::string> url{};

    friend bool operator==(const AirtableButton&, const AirtableButton&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::AirtableButton> {
    static myairtable::AirtableButton from_json(const json& j) {
        return {
            myairtable::read_field<std::string>(j, "label"),
            myairtable::read_field<std::string>(j, "url"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableButton& b) {
        j = json::object();
        myairtable::write_optional(j, "label", b.label);
        myairtable::write_optional(j, "url", b.url);
    }
};

} // namespace nlohmann
