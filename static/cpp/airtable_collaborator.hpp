#pragma once

#include <optional>
#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// An Airtable collaborator (user). Construct for writes with just an id:
/// `AirtableCollaborator{.id = "usr..."}`.
struct AirtableCollaborator {
    std::optional<std::string> id{};
    std::optional<std::string> email{};
    std::optional<std::string> name{};
    std::optional<std::string> profile_pic_url{};

    friend bool operator==(const AirtableCollaborator&, const AirtableCollaborator&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::AirtableCollaborator> {
    static myairtable::AirtableCollaborator from_json(const json& j) {
        return {
            myairtable::read_field<std::string>(j, "id"),
            myairtable::read_field<std::string>(j, "email"),
            myairtable::read_field<std::string>(j, "name"),
            myairtable::read_field<std::string>(j, "profilePicUrl"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableCollaborator& c) {
        j = json::object();
        myairtable::write_optional(j, "id", c.id);
        myairtable::write_optional(j, "email", c.email);
        myairtable::write_optional(j, "name", c.name);
        myairtable::write_optional(j, "profilePicUrl", c.profile_pic_url);
    }
};

} // namespace nlohmann
