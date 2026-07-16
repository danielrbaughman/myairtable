#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "airtable_json.hpp"

namespace myairtable {

/// An untyped field bag backing `DictTable`. Stores raw json values keyed by
/// field id, with dual access: get/set accept either a field id (tried first)
/// or a field name (resolved via the generated name→id map).
///
/// A json value of null is meaningful: it clears the field server-side. Use
/// `remove()` to drop a key from the payload entirely.
class Fields {
  public:
    Fields() = default;
    explicit Fields(std::map<std::string, json, std::less<>> storage,
                    std::map<std::string, std::string, std::less<>> name_to_id = {})
        : storage_(std::move(storage)), name_to_id_(std::move(name_to_id)) {}

    /// Field name → field id, supplied by the generated table so names resolve.
    void set_name_to_id(std::map<std::string, std::string, std::less<>> name_to_id) {
        name_to_id_ = std::move(name_to_id);
    }
    const std::map<std::string, std::string, std::less<>>& name_to_id() const {
        return name_to_id_;
    }

    size_t count() const { return storage_.size(); }

    std::vector<std::string> ids() const {
        std::vector<std::string> out;
        out.reserve(storage_.size());
        for (const auto& [key, value] : storage_) {
            out.push_back(key);
        }
        return out;
    }

    const std::map<std::string, json, std::less<>>& to_map() const { return storage_; }

    /// Id-first lookup, name fallback; JSON null when absent (BLANK semantics).
    json get(std::string_view key) const {
        if (const auto it = storage_.find(key); it != storage_.end()) {
            return it->second;
        }
        if (const auto name = name_to_id_.find(key); name != name_to_id_.end()) {
            if (const auto it = storage_.find(name->second); it != storage_.end()) {
                return it->second;
            }
        }
        return json(nullptr);
    }

    bool has(std::string_view key) const {
        if (storage_.contains(key)) {
            return true;
        }
        const auto name = name_to_id_.find(key);
        return name != name_to_id_.end() && storage_.contains(name->second);
    }

    /// Id-first store: an existing storage key wins, then a known name resolves
    /// to its id, then the raw key is used as-is.
    void set(std::string_view key, json value) {
        if (const auto it = storage_.find(key); it != storage_.end()) {
            it->second = std::move(value);
            return;
        }
        if (const auto name = name_to_id_.find(key); name != name_to_id_.end()) {
            storage_.insert_or_assign(name->second, std::move(value));
            return;
        }
        storage_.insert_or_assign(std::string(key), std::move(value));
    }

    /// Remove the entry entirely (vs storing JSON null, which clears server-side).
    void remove(std::string_view key) {
        if (const auto it = storage_.find(key); it != storage_.end()) {
            storage_.erase(it);
            return;
        }
        if (const auto name = name_to_id_.find(key); name != name_to_id_.end()) {
            storage_.erase(name->second);
        }
    }

    // ---- typed convenience accessors -----------------------------------------

    std::optional<std::string> get_string(std::string_view key) const {
        const json value = get(key);
        return value.is_string() ? std::optional(value.get<std::string>()) : std::nullopt;
    }
    std::optional<int64_t> get_long(std::string_view key) const {
        const json value = get(key);
        return value.is_number() ? std::optional(static_cast<int64_t>(value.get<double>()))
                                 : std::nullopt;
    }
    std::optional<double> get_double(std::string_view key) const {
        const json value = get(key);
        return value.is_number() ? std::optional(value.get<double>()) : std::nullopt;
    }
    std::optional<bool> get_bool(std::string_view key) const {
        const json value = get(key);
        return value.is_boolean() ? std::optional(value.get<bool>()) : std::nullopt;
    }
    std::optional<std::vector<json>> get_array(std::string_view key) const {
        const json value = get(key);
        return value.is_array() ? std::optional(std::vector<json>(value.begin(), value.end()))
                                : std::nullopt;
    }

    void set_string(std::string_view key, const std::optional<std::string>& value) {
        set(key, value.has_value() ? json(*value) : json(nullptr));
    }
    void set_long(std::string_view key, std::optional<int64_t> value) {
        set(key, value.has_value() ? json(*value) : json(nullptr));
    }
    void set_double(std::string_view key, std::optional<double> value) {
        set(key, value.has_value() ? json(*value) : json(nullptr));
    }
    void set_bool(std::string_view key, std::optional<bool> value) {
        set(key, value.has_value() ? json(*value) : json(nullptr));
    }
    void set_strings(std::string_view key, const std::optional<std::vector<std::string>>& value) {
        set(key, value.has_value() ? json(*value) : json(nullptr));
    }

    /// Deep value equality on storage; the name→id map is metadata, not state.
    friend bool operator==(const Fields& a, const Fields& b) { return a.storage_ == b.storage_; }

  private:
    std::map<std::string, json, std::less<>> storage_;
    std::map<std::string, std::string, std::less<>> name_to_id_;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::Fields> {
    static myairtable::Fields from_json(const json& j) {
        std::map<std::string, json, std::less<>> storage;
        if (j.is_object()) {
            for (const auto& [key, value] : j.items()) {
                storage[key] = value;
            }
        }
        return myairtable::Fields(std::move(storage));
    }
    /// Serialization round-trips storage only — the name→id map is not state.
    static void to_json(json& j, const myairtable::Fields& fields) {
        j = json::object();
        for (const auto& [key, value] : fields.to_map()) {
            j[key] = value;
        }
    }
};

} // namespace nlohmann
