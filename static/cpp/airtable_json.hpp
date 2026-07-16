#pragma once

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

} // namespace myairtable
