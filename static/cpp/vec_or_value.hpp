#pragma once

#include <optional>
#include <utility>
#include <variant>
#include <vector>

#include "airtable_json.hpp"
#include "maybe_special_or_error.hpp"

namespace myairtable {

/// A lookup/rollup field's decoded state: a single `T` or an array of nullable
/// `T` — Airtable's metadata cannot promise which shape a given record returns.
///
/// `Multiple` holds `std::optional<T>` elements because lookup arrays can carry
/// nulls (the C# `List<T?>` / Java nullable-item analog). Null elements are
/// preserved on decode AND re-encode; `clean_values()` is the lossy flattening
/// accessor.
template <typename T> class VecOrValue {
  public:
    using value_type = T;

    VecOrValue() = default;
    explicit VecOrValue(T single) : data_(std::move(single)) {}
    explicit VecOrValue(std::vector<std::optional<T>> multiple) : data_(std::move(multiple)) {}

    /// The single value, or nullopt when this holds the array shape.
    std::optional<T> value() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return *v;
        }
        return std::nullopt;
    }

    /// Both shapes as a nullable-element vector (Single x -> [x]).
    std::vector<std::optional<T>> values() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return {*v};
        }
        return std::get<std::vector<std::optional<T>>>(data_);
    }

    /// Flatten to plain values: drops null elements, and — when `T` is a
    /// MaybeSpecialOrError — also drops special/error cases, yielding the
    /// inner values (the cross-target CleanValues DX helper).
    auto clean_values() const {
        if constexpr (is_maybe_special_or_error<T>::value) {
            std::vector<typename T::value_type> out;
            for (const auto& item : values()) {
                if (item.has_value()) {
                    if (auto inner = item->value()) {
                        out.push_back(*inner);
                    }
                }
            }
            return out;
        } else {
            std::vector<T> out;
            for (const auto& item : values()) {
                if (item.has_value()) {
                    out.push_back(*item);
                }
            }
            return out;
        }
    }

    bool is_single() const { return std::holds_alternative<T>(data_); }
    bool is_multiple() const { return !is_single(); }

    /// std::visit escape hatch.
    const std::variant<T, std::vector<std::optional<T>>>& raw() const { return data_; }

    friend bool operator==(const VecOrValue&, const VecOrValue&) = default;

  private:
    std::variant<T, std::vector<std::optional<T>>> data_;
};

} // namespace myairtable

namespace nlohmann {

template <typename T> struct adl_serializer<myairtable::VecOrValue<T>> {
    static myairtable::VecOrValue<T> from_json(const json& j) {
        using Out = myairtable::VecOrValue<T>;
        if (j.is_array()) {
            std::vector<std::optional<T>> items;
            items.reserve(j.size());
            for (const auto& element : j) {
                // Element null-handling lives HERE, in a serializer for a type
                // we own — never as an adl_serializer<std::optional<T>> (ODR).
                if (element.is_null()) {
                    items.push_back(std::nullopt);
                } else {
                    items.push_back(element.get<T>());
                }
            }
            return Out(std::move(items));
        }
        return Out(j.get<T>());
    }
    static void to_json(json& j, const myairtable::VecOrValue<T>& v) {
        if (v.is_single()) {
            j = *v.value();
            return;
        }
        j = json::array();
        for (const auto& item : v.values()) {
            if (item.has_value()) {
                j.push_back(json(*item));
            } else {
                j.push_back(nullptr);
            }
        }
    }
};

} // namespace nlohmann
