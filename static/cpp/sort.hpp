#pragma once

#include <string>
#include <string_view>

namespace myairtable {

/// Sort direction; wire values are `asc` / `desc`.
enum class SortDirection {
    Asc,
    Desc,
};

/// The Airtable wire value for a sort direction.
inline std::string_view wire(SortDirection direction) {
    return direction == SortDirection::Desc ? "desc" : "asc";
}

/// A sort spec for a list query: a field (name or id) and a direction.
struct Sort {
    std::string field;
    SortDirection direction = SortDirection::Asc;

    friend bool operator==(const Sort&, const Sort&) = default;
};

} // namespace myairtable
