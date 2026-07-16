#pragma once

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "airtable_client.hpp"
#include "airtable_date.hpp"
#include "airtable_exception.hpp"
#include "airtable_json.hpp"
#include "airtable_query.hpp"

namespace myairtable {

/// Typed record accessor for an Airtable table. Forwards all I/O to the
/// AirtableClient; decodes responses into the generated `{Table}Model`
/// aggregates (ADL from_json over the full record envelope), attaching the
/// client + taking a snapshot on every decode so model-side save()/
/// dirty_fields() work. C++ templates carry the model type — no class token.
///
/// `M` contract (provided by every generated model):
///   static constexpr std::string_view kTableId;
///   std::optional<std::string> id;  std::optional<DateTime> created_time;
///   std::shared_ptr<AirtableClient> client_;  json snapshot_;
///   take_snapshot() / dirty_fields() / to_create_fields()  (CRTP base)
template <typename M> class OrmTable {
  public:
    /// Airtable's hard cap for create / update / delete batches.
    static constexpr size_t kBatchSize = 10;

    /// Result of upsert(): the merged model plus whether it was inserted.
    struct UpsertResult {
        M model;
        bool was_created = false;
    };

    explicit OrmTable(std::shared_ptr<AirtableClient> client)
        : table_id_(std::string(M::kTableId)), client_(std::move(client)) {}

    const std::string& table_id() const { return table_id_; }
    const std::shared_ptr<AirtableClient>& client() const { return client_; }

    // ---- get (read) -----------------------------------------------------------

    /// Fetch one record by ID.
    M get_one(const std::string& record_id) const {
        return decode_envelope(parse_tree(client_->get_record(table_id_, record_id)));
    }

    /// Fetch many records by ID (sequential — the client is blocking);
    /// preserves caller-supplied order.
    std::vector<M> get_many(const std::vector<std::string>& record_ids) const {
        std::vector<M> collected;
        collected.reserve(record_ids.size());
        for (const auto& record_id : record_ids) {
            collected.push_back(get_one(record_id));
        }
        return collected;
    }

    /// Fetch all records (default query).
    std::vector<M> get_many() const { return get_many(AirtableQuery{}); }

    /// Fetch records matching the query. Paginates internally via the `offset`
    /// continuation token; returns the merged list in page-arrival order.
    std::vector<M> get_many(const AirtableQuery& query) const {
        std::vector<M> collected;
        std::optional<std::string> offset;
        do {
            std::string payload;
            if (offset.has_value()) {
                auto params = query.to_parameters();
                params.emplace_back("offset", *offset);
                payload = client_->send("GET", client_->table_url(table_id_, params), std::nullopt,
                                        /*idempotent=*/true);
            } else {
                payload = client_->list_records(table_id_, query);
            }
            const json page = parse_tree(payload);
            if (page.contains("records")) {
                for (const auto& envelope : page.at("records")) {
                    collected.push_back(decode_envelope(envelope));
                }
            }
            offset = page.contains("offset") && page.at("offset").is_string()
                         ? std::optional(page.at("offset").get<std::string>())
                         : std::nullopt;
        } while (offset.has_value() && !offset->empty());
        return collected;
    }

    // ---- create -----------------------------------------------------------------

    /// Create one record from a fresh model built with a designated initializer
    /// (e.g. `PrimaryModel{.primary_key = "x"}`); only writable fields are sent.
    M create_one(const M& model, bool typecast = false) const {
        auto created = create_batch({model.to_create_fields()}, typecast);
        if (created.empty()) {
            throw ApiError("UNEXPECTED_RESPONSE", "create returned no records");
        }
        return std::move(created.front());
    }

    /// Create many records. Chunks into Airtable's batch limit (10).
    std::vector<M> create_many(const std::vector<M>& models, bool typecast = false) const {
        std::vector<M> collected;
        collected.reserve(models.size());
        std::vector<json> payloads;
        payloads.reserve(models.size());
        for (const auto& model : models) {
            payloads.push_back(model.to_create_fields());
        }
        for (size_t start = 0; start < payloads.size(); start += kBatchSize) {
            const std::vector<json> batch(
                payloads.begin() + static_cast<long>(start),
                payloads.begin() +
                    static_cast<long>(std::min(start + kBatchSize, payloads.size())));
            for (auto& model : create_batch(batch, typecast)) {
                collected.push_back(std::move(model));
            }
        }
        return collected;
    }

    // ---- update -----------------------------------------------------------------

    /// Update a single model: diffs against the model's snapshot and sends only
    /// fields that changed. A clean model is returned as-is, never PATCHed.
    M update_one(const M& model, bool typecast = false) const {
        auto updated = update_many(std::vector<M>{model}, typecast);
        if (updated.empty()) {
            throw ApiError("UNEXPECTED_RESPONSE", "update returned no records");
        }
        return std::move(updated.front());
    }

    /// Update many models (dirty fields only). Clean models come back unchanged
    /// in their original positions.
    std::vector<M> update_many(const std::vector<M>& models, bool typecast = false) const {
        std::vector<std::optional<M>> results(models.size());
        std::vector<size_t> dirty_indices;
        std::vector<std::pair<std::string, json>> patches;
        for (size_t index = 0; index < models.size(); ++index) {
            const M& model = models[index];
            if (!model.id.has_value() || model.id->empty()) {
                throw ApiError("UNSAVED_MODEL", "Cannot update a model without an id");
            }
            json dirty = model.dirty_fields();
            if (dirty.empty()) {
                results[index] = model;
            } else {
                dirty_indices.push_back(index);
                patches.emplace_back(*model.id, std::move(dirty));
            }
        }
        std::vector<M> updated;
        for (size_t start = 0; start < patches.size(); start += kBatchSize) {
            const std::vector<std::pair<std::string, json>> batch(
                patches.begin() + static_cast<long>(start),
                patches.begin() + static_cast<long>(std::min(start + kBatchSize, patches.size())));
            for (auto& model : update_batch(batch, typecast)) {
                updated.push_back(std::move(model));
            }
        }
        if (updated.size() < dirty_indices.size()) {
            throw ApiError("UNEXPECTED_RESPONSE", "update returned fewer records than requested");
        }
        for (size_t i = 0; i < dirty_indices.size(); ++i) {
            results[dirty_indices[i]] = std::move(updated[i]);
        }
        std::vector<M> ordered;
        ordered.reserve(results.size());
        for (auto& result : results) {
            if (!result.has_value()) {
                throw ApiError("UNEXPECTED_RESPONSE",
                               "update returned fewer records than requested");
            }
            ordered.push_back(std::move(*result));
        }
        return ordered;
    }

    /// Update a record's fields directly by ID (no model required).
    M update_fields(const std::string& record_id, const json& fields, bool typecast = false) const {
        auto updated = update_batch({{record_id, fields}}, typecast);
        if (updated.empty()) {
            throw ApiError("UNEXPECTED_RESPONSE", "update returned no records");
        }
        return std::move(updated.front());
    }

    // ---- upsert -----------------------------------------------------------------

    /// Upsert a record, matching on the supplied field IDs. Returns the merged
    /// model plus whether the record was inserted (vs updated).
    UpsertResult upsert(const M& model, const std::vector<std::string>& fields_to_merge_on,
                        bool typecast = false) const {
        json body = json::object();
        body["records"] = json::array({json{{"fields", model.to_create_fields()}}});
        body["performUpsert"] = json{{"fieldsToMergeOn", fields_to_merge_on}};
        body["returnFieldsByFieldId"] = true;
        if (typecast) {
            body["typecast"] = true;
        }
        // A merge-keyed upsert is idempotent (the key determines identity, a
        // retry converges); an empty merge list inserts and is NOT.
        const std::string payload = client_->update_records(
            table_id_, body.dump(), /*idempotent=*/!fields_to_merge_on.empty());
        const json parsed = parse_tree(payload);
        if (!parsed.contains("records") || parsed.at("records").empty()) {
            throw ApiError("UNEXPECTED_RESPONSE", "upsert returned no records");
        }
        M merged = decode_envelope(parsed.at("records").front());
        bool was_created = false;
        if (parsed.contains("createdRecords") && merged.id.has_value()) {
            for (const auto& created_id : parsed.at("createdRecords")) {
                if (created_id.is_string() && created_id.get<std::string>() == *merged.id) {
                    was_created = true;
                }
            }
        }
        return UpsertResult{std::move(merged), was_created};
    }

    // ---- delete -----------------------------------------------------------------

    void delete_one(const std::string& record_id) const {
        client_->delete_record(table_id_, record_id);
    }

    void delete_many(const std::vector<std::string>& record_ids) const {
        for (size_t start = 0; start < record_ids.size(); start += kBatchSize) {
            const std::vector<std::string> batch(
                record_ids.begin() + static_cast<long>(start),
                record_ids.begin() +
                    static_cast<long>(std::min(start + kBatchSize, record_ids.size())));
            client_->delete_records(table_id_, batch);
        }
    }

    /// Delete every record matching the query (default: the whole table).
    /// Returns the number of records deleted.
    size_t delete_all(const AirtableQuery& query = AirtableQuery{}) const {
        std::vector<std::string> ids;
        for (const auto& model : get_many(query)) {
            if (model.id.has_value()) {
                ids.push_back(*model.id);
            }
        }
        delete_many(ids);
        return ids.size();
    }

  private:
    /// Decode one `{id, createdTime, fields}` envelope, attach the client, and
    /// take the baseline snapshot so a table-produced model starts clean.
    M decode_envelope(const json& envelope) const {
        if (!envelope.is_object()) {
            throw DecodingError("expected a record object");
        }
        try {
            M model = envelope.get<M>();
            model.client_ = client_;
            model.take_snapshot();
            return model;
        } catch (const AirtableException&) {
            throw;
        } catch (const json::exception& error) {
            throw DecodingError(error.what());
        }
    }

    static json parse_tree(const std::string& payload) {
        json parsed = json::parse(payload, /*cb=*/nullptr, /*allow_exceptions=*/false);
        if (parsed.is_discarded()) {
            throw DecodingError("unparseable response payload");
        }
        return parsed;
    }

    std::vector<M> create_batch(const std::vector<json>& field_payloads, bool typecast) const {
        if (field_payloads.empty()) {
            return {};
        }
        json body = json::object();
        body["records"] = json::array();
        for (const auto& fields : field_payloads) {
            body["records"].push_back(json{{"fields", fields}});
        }
        body["returnFieldsByFieldId"] = true;
        if (typecast) {
            body["typecast"] = true;
        }
        return decode_list(client_->create_records(table_id_, body.dump()));
    }

    std::vector<M> update_batch(const std::vector<std::pair<std::string, json>>& patches,
                                bool typecast) const {
        if (patches.empty()) {
            return {};
        }
        json body = json::object();
        body["records"] = json::array();
        for (const auto& [record_id, fields] : patches) {
            body["records"].push_back(json{{"id", record_id}, {"fields", fields}});
        }
        body["returnFieldsByFieldId"] = true;
        if (typecast) {
            body["typecast"] = true;
        }
        return decode_list(client_->update_records(table_id_, body.dump()));
    }

    std::vector<M> decode_list(const std::string& payload) const {
        const json parsed = parse_tree(payload);
        std::vector<M> records;
        if (parsed.contains("records")) {
            for (const auto& envelope : parsed.at("records")) {
                records.push_back(decode_envelope(envelope));
            }
        }
        return records;
    }

    std::string table_id_;
    std::shared_ptr<AirtableClient> client_;
};

} // namespace myairtable
