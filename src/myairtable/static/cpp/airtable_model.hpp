#pragma once

#include <memory>
#include <string>

#include "airtable_client.hpp"
#include "airtable_exception.hpp"
#include "airtable_json.hpp"
#include "orm_table.hpp"

namespace myairtable {

/// CRTP behavior base for every generated `{Table}Model` aggregate.
///
/// Deliberately holds NO data — the derived model stays an aggregate (so
/// designated-initializer creation works) and declares the state members
/// directly: `id`, `created_time`, `client_`, `snapshot_`, plus the three
/// generated hooks `collect_writable_fields()` / `collect_computed_fields()` /
/// `detach_attachments_for_copy()` and the `kTableId` constant. Everything else — snapshotting,
/// dirty diffing, payload building, the fluent save/fetch/remove — lives here so the generator
/// emits no boilerplate.
///
/// Computed fields are public members on the aggregate (no `private set` in
/// C++): mutating one and calling save() silently sends NOTHING for it —
/// write paths serialize writable fields only (plan R21, pinned by tests).
template <typename Derived> struct AirtableModel {
    /// `true` when the model has no server-assigned ID yet.
    bool is_new() const { return !derived().id.has_value() || derived().id->empty(); }

    /// Capture current writable values as the baseline for dirty_fields().
    /// Tables snapshot on every decode, so table-produced models start clean.
    /// Note: save() returns a FRESH, freshly-snapshotted instance; the model
    /// you called save() on keeps its pre-save snapshot.
    void take_snapshot() { derived().snapshot_ = derived().collect_writable_fields(); }

    /// Writable fields that changed since the last take_snapshot(), keyed by
    /// field ID. Cleared fields appear as JSON null. Structural (deep)
    /// equality — never the formula-coercion is_equal, whose first-element
    /// array compare would miss a multi-value change like [a, b] -> [a].
    json dirty_fields() const {
        const json current = derived().collect_writable_fields();
        const json& snapshot = derived().snapshot_;
        json dirty = json::object();
        for (const auto& [field_id, value] : current.items()) {
            if (!snapshot.is_object() || !snapshot.contains(field_id) ||
                snapshot.at(field_id) != value) {
                dirty[field_id] = value;
            }
        }
        return dirty;
    }

    /// All current non-null field values (writable + computed), keyed by field ID.
    json to_record() const {
        // Bind the collected temporaries to locals: `.items()` over a temporary
        // json is a stack-use-after-scope in C++20 (range-for lifetime extension
        // does not reach through the proxy) — ASan-caught in F4.1.
        const json writable = derived().collect_writable_fields();
        const json computed = derived().collect_computed_fields();
        json record = json::object();
        for (const auto& [field_id, value] : writable.items()) {
            if (!value.is_null()) {
                record[field_id] = value;
            }
        }
        for (const auto& [field_id, value] : computed.items()) {
            if (!value.is_null()) {
                record[field_id] = value;
            }
        }
        return record;
    }

    /// Non-null WRITABLE field values keyed by field ID — the create payload.
    json to_create_fields() const {
        const json writable = derived().collect_writable_fields();
        json fields = json::object();
        for (const auto& [field_id, value] : writable.items()) {
            if (!value.is_null()) {
                fields[field_id] = value;
            }
        }
        return fields;
    }

    const std::string& require_id() const {
        if (is_new()) {
            throw ApiError("UNSAVED_MODEL", "model has no record id");
        }
        return *derived().id;
    }

    const std::shared_ptr<AirtableClient>& require_client() const {
        if (derived().client_ == nullptr) {
            throw ApiError("DETACHED_MODEL",
                           "model has no attached client; fetch it through a table first");
        }
        return derived().client_;
    }

    /// A detached, unsaved copy of this record, ready to hand to `create_one(...)`.
    ///
    /// NOT the copy constructor. `Derived b = a;` clones the record's IDENTITY too:
    /// `b` still carries `a`'s `id`, so `b.save()` PATCHES the source row. `copy()`
    /// is the detaching clone -- same values, no identity -- which is why it earns a
    /// name in a language where copying is already a built-in operation.
    ///
    /// Carries every field value, computed ones included, so the copy READS like its
    /// source. That is safe on the wire because the create path builds its body from
    /// `to_create_fields()`, which walks `collect_writable_fields()` only -- a computed
    /// value can never reach the POST. It does mean carried computed values are
    /// semantically STALE on the clone: a formula over `RECORD_ID()` shows the SOURCE's
    /// id until the copy is saved and re-read. That is the accepted cost.
    ///
    /// Detached: `id` and `created_time` are cleared (so `is_new()` is true) and
    /// `snapshot_` is reset to JSON null rather than an empty object, so `dirty_fields()`
    /// reports EVERY writable value rather than nothing -- the trap the other targets hit
    /// when a copy kept a full snapshot and POSTed `{"fields":{}}`. `take_snapshot()` is
    /// deliberately NOT called here for the same reason. The client handle is KEPT, so
    /// `record.copy().save()`-shaped flows still reach the table.
    ///
    /// Performs no I/O -- that is the whole difference from the table's `duplicate_one()`,
    /// which re-reads the source from Airtable first. A copy is therefore only as fresh as
    /// the model in hand, which matters most for attachments: their signed URLs expire
    /// after roughly two hours.
    ///
    /// Writable attachment cells are projected to `{url, filename}` here, because
    /// `create_one(...)` does NOT project and Airtable rejects the `id`/`size`/`type` an
    /// attachment read back from the server carries. Computed attachment-shaped cells keep
    /// their full metadata: they are never written back.
    ///
    /// Every other cell is deep-copied for free -- the models are aggregates of
    /// value-semantic members (`std::optional`, `std::vector`, `std::string`, `json`), so
    /// the implicit copy shares no mutable state with the source. `client_` is the one
    /// deliberate exception: a `shared_ptr` whose pointee is shared on purpose.
    ///
    /// Linked records are copied as-is. Airtable links are many-to-many, so the copy is
    /// added alongside the original and this record's own links are untouched.
    Derived copy() const {
        Derived copied = derived();
        copied.id.reset();
        copied.created_time.reset();
        copied.snapshot_ = json{};
        // client_ is intentionally left in place (contract item 4).
        copied.detach_attachments_for_copy();
        return copied;
    }

    // ---- fluent CRUD (the C# ModelOps analog; templates need no class token) ----

    /// Persist this model's dirty fields. Requires a saved record — construct a
    /// fresh model and pass it to the table's create_one(...) to insert a new row.
    Derived save(bool typecast = false) const {
        if (is_new()) {
            throw ApiError(
                "UNSAVED_MODEL",
                "Cannot save a model without an id; use the table's create_one(...) instead");
        }
        return OrmTable<Derived>(require_client()).update_one(derived(), typecast);
    }

    /// Re-fetch this model from the server. Returns a fresh instance.
    Derived fetch() const {
        if (is_new()) {
            throw ApiError("UNSAVED_MODEL", "Cannot fetch an unsaved model");
        }
        return OrmTable<Derived>(require_client()).get_one(require_id());
    }

    /// Delete the record referenced by this model's id. (`delete` is a C++
    /// keyword — the one forced naming divergence from the other targets.)
    void remove() const {
        if (is_new()) {
            throw ApiError("UNSAVED_MODEL", "Cannot delete an unsaved model");
        }
        require_client()->delete_record(std::string(Derived::kTableId), require_id());
    }

  private:
    Derived& derived() { return static_cast<Derived&>(*this); }
    const Derived& derived() const { return static_cast<const Derived&>(*this); }
};

} // namespace myairtable
