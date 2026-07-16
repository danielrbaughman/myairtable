#pragma once

#include <string>

#include "airtable_date.hpp"
#include "airtable_json.hpp"

namespace myairtable {

/// The Airtable REST envelope for one record: id, createdTime, and the raw
/// fields object (typed models decode from `fields` separately).
struct AirtableRecord {
    std::string id{};
    DateTime created_time{};
    json fields = json::object();

    friend bool operator==(const AirtableRecord&, const AirtableRecord&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::AirtableRecord> {
    static myairtable::AirtableRecord from_json(const json& j) {
        myairtable::AirtableRecord record;
        record.id = j.at("id").get<std::string>();
        if (j.contains("createdTime")) {
            record.created_time = j.at("createdTime").get<myairtable::DateTime>();
        }
        if (j.contains("fields")) {
            record.fields = j.at("fields");
        }
        return record;
    }
    static void to_json(json& j, const myairtable::AirtableRecord& record) {
        j = json{
            {"id", record.id}, {"createdTime", record.created_time}, {"fields", record.fields}};
    }
};

} // namespace nlohmann
