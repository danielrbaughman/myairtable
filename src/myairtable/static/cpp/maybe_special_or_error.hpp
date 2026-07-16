#pragma once

#include <optional>
#include <type_traits>
#include <utility>
#include <variant>

#include "airtable_json.hpp"
#include "error_value.hpp"
#include "special_number.hpp"

namespace myairtable {

/// A computed field's decoded state: a plain value, a special number
/// (`{"specialValue": "NaN"}`), or an error (`{"error": "#ERROR!"}`).
///
/// The idiomatic C++ analog of the Rust enum / Kotlin sealed interface /
/// Java+C# sealed records used by the other targets: a `std::variant` wrapper
/// with public constructors (the adl_serializer constructs through them) and
/// DX accessors. Pattern-match via `raw()` + `std::visit` when needed.
template <typename T> class MaybeSpecialOrError {
  public:
    using value_type = T;

    MaybeSpecialOrError() = default;
    explicit MaybeSpecialOrError(T value) : data_(std::move(value)) {}
    explicit MaybeSpecialOrError(SpecialNumber special) : data_(std::move(special)) {}
    explicit MaybeSpecialOrError(ErrorValue error) : data_(std::move(error)) {}

    /// The plain value, or nullopt when this holds a special/error case.
    std::optional<T> value() const {
        if (const T* v = std::get_if<T>(&data_)) {
            return *v;
        }
        return std::nullopt;
    }

    std::optional<SpecialNumber> special() const {
        if (const auto* s = std::get_if<SpecialNumber>(&data_)) {
            return *s;
        }
        return std::nullopt;
    }

    std::optional<ErrorValue> error() const {
        if (const auto* e = std::get_if<ErrorValue>(&data_)) {
            return *e;
        }
        return std::nullopt;
    }

    bool is_value() const { return std::holds_alternative<T>(data_); }
    bool is_special() const { return std::holds_alternative<SpecialNumber>(data_); }
    bool is_error() const { return std::holds_alternative<ErrorValue>(data_); }

    /// std::visit escape hatch.
    const std::variant<T, SpecialNumber, ErrorValue>& raw() const { return data_; }

    friend bool operator==(const MaybeSpecialOrError&, const MaybeSpecialOrError&) = default;

  private:
    std::variant<T, SpecialNumber, ErrorValue> data_;
};

/// Trait: is `T` a MaybeSpecialOrError instantiation? (Used by VecOrValue's
/// clean_values() to flatten nested computed wrappers.)
template <typename T> struct is_maybe_special_or_error : std::false_type {};
template <typename U> struct is_maybe_special_or_error<MaybeSpecialOrError<U>> : std::true_type {};

} // namespace myairtable

namespace nlohmann {

template <typename T> struct adl_serializer<myairtable::MaybeSpecialOrError<T>> {
    static myairtable::MaybeSpecialOrError<T> from_json(const json& j) {
        using Out = myairtable::MaybeSpecialOrError<T>;
        if (j.is_object() && j.contains("specialValue")) {
            return Out(j.get<myairtable::SpecialNumber>());
        }
        if (j.is_object() && j.contains("error")) {
            return Out(j.get<myairtable::ErrorValue>());
        }
        return Out(j.get<T>()); // element recursion via the serializer machinery
    }
    static void to_json(json& j, const myairtable::MaybeSpecialOrError<T>& v) {
        // Untagged encoding: the value/special/error shapes are disjoint on the wire.
        if (auto s = v.special()) {
            j = *s;
        } else if (auto e = v.error()) {
            j = *e;
        } else {
            j = *v.value();
        }
    }
};

} // namespace nlohmann
