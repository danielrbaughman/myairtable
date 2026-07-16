#pragma once

#include <map>
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
#include "fields.hpp"

namespace myairtable {

/// Untyped (field-bag) table access: records travel as `Fields`, keyed by
/// field id with the generated name→id map attached for dual access. The typed
/// ORM surface (`OrmTable`, F4) is the default; this is the raw escape hatch.
class DictTable {
  public:
    static constexpr size_t kBatchSize = 10;

    struct Record {
        std::string id;
        DateTime created_time{};
        Fields fields;
    };

    struct Update {
        std::string id;
        Fields fields;
    };

    DictTable(std::shared_ptr<AirtableClient> client, std::string table_id,
              std::map<std::string, std::string, std::less<>> name_to_id = {})
        : client_(std::move(client)), table_id_(std::move(table_id)),
          name_to_id_(std::move(name_to_id)) {}

    const std::string& table_id() const { return table_id_; }
    const std::shared_ptr<AirtableClient>& client() const { return client_; }

    // ---- reads -----------------------------------------------------------------

    Record get(const std::string& record_id) const {
        return to_record(decode(client_->get_record(table_id_, record_id)));
    }

    std::vector<Record> get_all() const { return get_all(AirtableQuery{}); }

    /// Fetch every page for `query` (eager offset-loop accumulation). The
    /// first page rides the client cache; continuation pages are always live
    /// (their offset tokens are transient and single-use).
    std::vector<Record> get_all(const AirtableQuery& query) const {
        std::vector<Record> records;
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
            const json page = decode(payload);
            if (page.contains("records")) {
                for (const auto& raw : page.at("records")) {
                    records.push_back(to_record(raw));
                }
            }
            offset = page.contains("offset") && page.at("offset").is_string()
                         ? std::optional(page.at("offset").get<std::string>())
                         : std::nullopt;
        } while (offset.has_value() && !offset->empty());
        return records;
    }

    // ---- creates ----------------------------------------------------------------

    Record create(const Fields& fields, bool typecast = false) const {
        return create(std::vector<Fields>{fields}, typecast).front();
    }

    std::vector<Record> create(const std::vector<Fields>& fields, bool typecast = false) const {
        std::vector<Record> created;
        created.reserve(fields.size());
        for (size_t start = 0; start < fields.size(); start += kBatchSize) {
            json body = json::object();
            body["records"] = json::array();
            for (size_t i = start; i < std::min(start + kBatchSize, fields.size()); ++i) {
                body["records"].push_back(json{{"fields", json(fields[i])}});
            }
            body["returnFieldsByFieldId"] = true;
            if (typecast) {
                body["typecast"] = true;
            }
            append_records(created, client_->create_records(table_id_, body.dump()));
        }
        return created;
    }

    // ---- updates -----------------------------------------------------------------

    Record update(const std::string& record_id, const Fields& fields, bool typecast = false) const {
        return update(std::vector<Update>{{record_id, fields}}, typecast).front();
    }

    std::vector<Record> update(const std::vector<Update>& updates, bool typecast = false) const {
        std::vector<Record> updated;
        updated.reserve(updates.size());
        for (size_t start = 0; start < updates.size(); start += kBatchSize) {
            json body = json::object();
            body["records"] = json::array();
            for (size_t i = start; i < std::min(start + kBatchSize, updates.size()); ++i) {
                body["records"].push_back(
                    json{{"id", updates[i].id}, {"fields", json(updates[i].fields)}});
            }
            body["returnFieldsByFieldId"] = true;
            if (typecast) {
                body["typecast"] = true;
            }
            append_records(updated, client_->update_records(table_id_, body.dump()));
        }
        return updated;
    }

    // ---- deletes ------------------------------------------------------------------

    void remove(const std::string& record_id) const {
        client_->delete_record(table_id_, record_id);
    }

    void remove(const std::vector<std::string>& record_ids) const {
        for (size_t start = 0; start < record_ids.size(); start += kBatchSize) {
            const std::vector<std::string> batch(
                record_ids.begin() + static_cast<long>(start),
                record_ids.begin() +
                    static_cast<long>(std::min(start + kBatchSize, record_ids.size())));
            client_->delete_records(table_id_, batch);
        }
    }

  private:
    Record to_record(const json& raw) const {
        Record record;
        record.id = raw.at("id").get<std::string>();
        if (raw.contains("createdTime")) {
            record.created_time = raw.at("createdTime").get<DateTime>();
        }
        Fields fields = raw.contains("fields") ? raw.at("fields").get<Fields>() : Fields{};
        fields.set_name_to_id(name_to_id_);
        record.fields = std::move(fields);
        return record;
    }

    void append_records(std::vector<Record>& out, const std::string& payload) const {
        const json parsed = decode(payload);
        if (parsed.contains("records")) {
            for (const auto& raw : parsed.at("records")) {
                out.push_back(to_record(raw));
            }
        }
    }

    static json decode(const std::string& payload) {
        json parsed = json::parse(payload, /*cb=*/nullptr, /*allow_exceptions=*/false);
        if (parsed.is_discarded()) {
            throw DecodingError("unparseable response payload");
        }
        return parsed;
    }

    std::shared_ptr<AirtableClient> client_;
    std::string table_id_;
    std::map<std::string, std::string, std::less<>> name_to_id_;
};

} // namespace myairtable
