#pragma once

#include <optional>
#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// An Airtable AI text field value (read-only on the wire): the generated text and where
/// its generation stands. `state` is `empty`, `loading`, `generated` or `error`;
/// `error_type` is set only for `error`.
struct AirtableAiText {
    std::optional<std::string> state{};
    std::optional<bool> is_stale{};
    std::optional<std::string> value{};
    std::optional<std::string> error_type{};

    friend bool operator==(const AirtableAiText&, const AirtableAiText&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::AirtableAiText> {
    static myairtable::AirtableAiText from_json(const json& j) {
        return {
            myairtable::read_field<std::string>(j, "state"),
            myairtable::read_field<bool>(j, "isStale"),
            myairtable::read_field<std::string>(j, "value"),
            myairtable::read_field<std::string>(j, "errorType"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableAiText& t) {
        j = json::object();
        myairtable::write_optional(j, "state", t.state);
        myairtable::write_optional(j, "isStale", t.is_stale);
        myairtable::write_optional(j, "value", t.value);
        myairtable::write_optional(j, "errorType", t.error_type);
    }
};

} // namespace nlohmann
