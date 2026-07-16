#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "sort.hpp"

namespace myairtable {

/// Marker for generated `{Table}View` enums: anything that names a view id.
/// (The generated view types provide `id()`; a raw string works everywhere too.)
struct AirtableViewRef {
    std::string id;
};

/// A list-query spec (filterByFormula, sort, fields, paging, view, ...).
///
/// A plain aggregate — build with designated initializers and mutate freely
/// (value semantics make copies independent, the C# `with`-expression analog):
///
///     AirtableQuery{.formula = "...", .max_records = 10,
///                   .sorts = {{.field = "Name", .direction = SortDirection::Desc}}}
struct AirtableQuery {
    std::optional<std::string> formula{};
    std::vector<Sort> sorts{};
    std::vector<std::string> fields{};
    std::optional<int> max_records{};
    std::optional<int> page_size{};
    std::optional<std::string> view{};
    /// Return cell data keyed by field id (the generated models decode by field id).
    bool return_fields_by_field_id = true;
    /// Wire cellFormat; only emitted when not "json" (the API default).
    std::string cell_format = "json";
    std::optional<std::string> time_zone{};
    std::optional<std::string> user_locale{};

    friend bool operator==(const AirtableQuery&, const AirtableQuery&) = default;

    /// Flatten to ordered query parameters (un-encoded; the client URL-encodes each).
    std::vector<std::pair<std::string, std::string>> to_parameters() const {
        std::vector<std::pair<std::string, std::string>> params;
        if (formula.has_value() && !formula->empty()) {
            params.emplace_back("filterByFormula", *formula);
        }
        for (const auto& field : fields) {
            params.emplace_back("fields[]", field);
        }
        for (size_t i = 0; i < sorts.size(); ++i) {
            const auto index = std::to_string(i);
            params.emplace_back("sort[" + index + "][field]", sorts[i].field);
            params.emplace_back("sort[" + index + "][direction]",
                                std::string(wire(sorts[i].direction)));
        }
        if (max_records.has_value()) {
            params.emplace_back("maxRecords", std::to_string(*max_records));
        }
        if (page_size.has_value()) {
            params.emplace_back("pageSize", std::to_string(*page_size));
        }
        if (view.has_value() && !view->empty()) {
            params.emplace_back("view", *view);
        }
        if (return_fields_by_field_id) {
            params.emplace_back("returnFieldsByFieldId", "true");
        }
        if (cell_format != "json") {
            params.emplace_back("cellFormat", cell_format);
        }
        if (time_zone.has_value() && !time_zone->empty()) {
            params.emplace_back("timeZone", *time_zone);
        }
        if (user_locale.has_value() && !user_locale->empty()) {
            params.emplace_back("userLocale", *user_locale);
        }
        return params;
    }
};

} // namespace myairtable
