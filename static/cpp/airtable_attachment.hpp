#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include "airtable_json.hpp"

namespace myairtable {

/// One thumbnail rendition.
struct AirtableThumbnail {
    std::optional<std::string> url{};
    std::optional<int64_t> width{};
    std::optional<int64_t> height{};

    friend bool operator==(const AirtableThumbnail&, const AirtableThumbnail&) = default;
};

/// Thumbnail set attached to an image attachment.
struct AirtableThumbnails {
    std::optional<AirtableThumbnail> small{};
    std::optional<AirtableThumbnail> large{};
    std::optional<AirtableThumbnail> full{};

    friend bool operator==(const AirtableThumbnails&, const AirtableThumbnails&) = default;
};

/// An Airtable attachment. Decoded from the API; for uploads, construct with
/// just a url (designated initializer): `AirtableAttachment{.url = "https://..."}`.
struct AirtableAttachment {
    std::optional<std::string> id{};
    std::optional<std::string> url{};
    std::optional<std::string> filename{};
    std::optional<int64_t> size{};
    std::optional<std::string> type{};
    std::optional<AirtableThumbnails> thumbnails{};

    friend bool operator==(const AirtableAttachment&, const AirtableAttachment&) = default;
};

} // namespace myairtable

namespace nlohmann {

template <> struct adl_serializer<myairtable::AirtableThumbnail> {
    static myairtable::AirtableThumbnail from_json(const json& j) {
        return {
            myairtable::read_field<std::string>(j, "url"),
            myairtable::read_field<int64_t>(j, "width"),
            myairtable::read_field<int64_t>(j, "height"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableThumbnail& t) {
        j = json::object();
        myairtable::write_optional(j, "url", t.url);
        myairtable::write_optional(j, "width", t.width);
        myairtable::write_optional(j, "height", t.height);
    }
};

template <> struct adl_serializer<myairtable::AirtableThumbnails> {
    static myairtable::AirtableThumbnails from_json(const json& j) {
        return {
            myairtable::read_field<myairtable::AirtableThumbnail>(j, "small"),
            myairtable::read_field<myairtable::AirtableThumbnail>(j, "large"),
            myairtable::read_field<myairtable::AirtableThumbnail>(j, "full"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableThumbnails& t) {
        j = json::object();
        myairtable::write_optional(j, "small", t.small);
        myairtable::write_optional(j, "large", t.large);
        myairtable::write_optional(j, "full", t.full);
    }
};

template <> struct adl_serializer<myairtable::AirtableAttachment> {
    static myairtable::AirtableAttachment from_json(const json& j) {
        return {
            myairtable::read_field<std::string>(j, "id"),
            myairtable::read_field<std::string>(j, "url"),
            myairtable::read_field<std::string>(j, "filename"),
            myairtable::read_field<int64_t>(j, "size"),
            myairtable::read_field<std::string>(j, "type"),
            myairtable::read_field<myairtable::AirtableThumbnails>(j, "thumbnails"),
        };
    }
    static void to_json(json& j, const myairtable::AirtableAttachment& a) {
        // Write-side: attachments are uploaded by url (+ optional filename);
        // decoded metadata is skipped when absent so upload payloads stay clean.
        j = json::object();
        myairtable::write_optional(j, "id", a.id);
        myairtable::write_optional(j, "url", a.url);
        myairtable::write_optional(j, "filename", a.filename);
        myairtable::write_optional(j, "size", a.size);
        myairtable::write_optional(j, "type", a.type);
        myairtable::write_optional(j, "thumbnails", a.thumbnails);
    }
};

} // namespace nlohmann
