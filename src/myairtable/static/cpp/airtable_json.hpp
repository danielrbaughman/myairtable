#pragma once

#include <algorithm>
#include <optional>
#include <string>

#include "vendor/nlohmann/json.hpp"

namespace myairtable {

/// The type-erased JSON value used throughout the runtime (value semantics,
/// deep `operator==`). BLANK in formula semantics is `json(nullptr)` — a JSON
/// null *value*, not a C++ null pointer.
using json = nlohmann::json;

/// Read an optional field from a decoded `fields` object.
///
/// Absent and JSON-null both map to `std::nullopt`. No
/// `adl_serializer<std::optional<T>>` is defined anywhere in this runtime:
/// specializing a serializer for a std type in a header-only library is a
/// program-wide ODR collision surface (a consumer or future nlohmann release
/// defining the same specialization would clash). These owned helpers are the
/// supported path for optional fields.
template <typename T> std::optional<T> read_field(const json& fields, const std::string& id) {
    const auto it = fields.find(id);
    if (it == fields.end() || it->is_null()) {
        return std::nullopt;
    }
    return it->template get<T>();
}

/// Write an optional field into an outgoing payload.
///
/// `std::nullopt` encodes as JSON null — an explicit null clears the field
/// server-side, which the dirty-diff machinery relies on.
template <typename T>
void write_field(json& out, const std::string& id, const std::optional<T>& value) {
    if (value.has_value()) {
        out[id] = *value;
    } else {
        out[id] = nullptr;
    }
}

/// Write an optional member, OMITTING it when absent (value-carrier encoding —
/// e.g. an attachment upload is `{"url": ...}` with no null metadata keys).
template <typename T>
void write_optional(json& out, const std::string& key, const std::optional<T>& value) {
    if (value.has_value()) {
        out[key] = *value;
    }
}

/// Reduce attachment cells to the only shape Airtable accepts when inserting.
///
/// Airtable returns attachments carrying read-only metadata (`id`, `size`, `type`, `width`,
/// `height`, `thumbnails`). On **create** it accepts only `{"url": ...}` (optionally with
/// `"filename"`) -- sending an `id`, alone or echoed alongside `url`, fails with
/// `INVALID_ATTACHMENT_OBJECT`. Airtable re-ingests the file and mints a fresh attachment id,
/// which is what makes a duplicated record's attachment independent of its source rather than
/// an alias.
///
/// Create-only: on **update** an `id` is legal and means "retain this attachment".
///
/// Cells are recognised by shape rather than by field id, so this needs no generated metadata:
/// no other Airtable cell type is an array of objects carrying a `url` alongside an
/// `att`-prefixed id. Returns a copy; the caller's json is never modified.
inline json project_attachments_for_create(const json& fields) {
    if (!fields.is_object()) {
        return fields;
    }
    json projected_fields = fields;
    for (auto entry : projected_fields.items()) {
        json& value = entry.value();
        if (!value.is_array() || value.empty()) {
            continue;
        }
        const bool is_attachment_cell =
            std::all_of(value.begin(), value.end(), [](const json& item) {
                if (!item.is_object() || !item.contains("url") || !item.contains("id")) {
                    return false;
                }
                const json& id = item.at("id");
                return id.is_string() && id.get<std::string>().rfind("att", 0) == 0;
            });
        if (!is_attachment_cell) {
            continue;
        }
        json projected = json::array();
        for (const json& item : value) {
            json projected_item = json::object();
            projected_item["url"] = item.at("url");
            if (item.contains("filename") && !item.at("filename").is_null()) {
                projected_item["filename"] = item.at("filename");
            }
            projected.push_back(std::move(projected_item));
        }
        value = std::move(projected);
    }
    return projected_fields;
}

} // namespace myairtable
