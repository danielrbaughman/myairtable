// AirtableModel::copy() -- the LOCAL half of duplicate(): detach the record's
// identity, keep every value, touch the network never.
//
// The C++-specific trap this file pins down is that `Derived b = a;` already
// compiles and already "copies": the implicit copy constructor clones the id too,
// so `b.save()` would PATCH the source row. copy() is the detaching clone, and
// these tests assert the four state members (id, created_time, snapshot_, client_)
// land exactly where the contract says -- three cleared, one deliberately kept.
//
// Hermetic by construction: copy() makes no calls, so the fake transport here
// exists only to prove that (a) a table-decoded model carries a client into its
// copy and (b) the copy's create payload is the one that would go on the wire.

#include <catch2/catch_test_macros.hpp>

#include "airtable_attachment.hpp"
#include "airtable_model.hpp"
#include "fake_transport.hpp"
#include "maybe_special_or_error.hpp"
#include "orm_table.hpp"

using namespace myairtable;
using myairtable_tests::FakeTransport;

namespace myairtable {

// Shaped exactly like write_models output (src/myairtable/generators/cpp.py), including
// the generated detach_attachments_for_copy() hook: writable attachment cells are listed,
// the computed attachment-shaped lookup deliberately is NOT.
struct CopyProbeModel : AirtableModel<CopyProbeModel> {
    static constexpr std::string_view kTableId = "tblCopyProbe";

    std::optional<std::string> id{};
    std::optional<DateTime> created_time{};
    std::shared_ptr<AirtableClient> client_{};
    json snapshot_{};

    std::optional<std::string> name{};                         // fldName   (writable)
    std::optional<std::vector<std::string>> tags{};            // fldTags   (writable)
    std::optional<std::vector<std::string>> links{};           // fldLinks  (writable, linked recs)
    std::optional<std::vector<AirtableAttachment>> photos{};   // fldPhotos (writable attachments)
    std::optional<MaybeSpecialOrError<int64_t>> auto_number{}; // fldAuto   (computed)
    std::optional<std::string> formula_id{};                   // fldFormula (computed)
    std::optional<std::vector<AirtableAttachment>>
        photo_lookup{}; // fldLookup (computed, attachment-shaped)

    json collect_writable_fields() const {
        json fields = json::object();
        write_field(fields, "fldName", name);
        write_field(fields, "fldTags", tags);
        write_field(fields, "fldLinks", links);
        write_field(fields, "fldPhotos", photos);
        return fields;
    }
    json collect_computed_fields() const {
        json fields = json::object();
        write_field(fields, "fldAuto", auto_number);
        write_field(fields, "fldFormula", formula_id);
        write_field(fields, "fldLookup", photo_lookup);
        return fields;
    }
    void detach_attachments_for_copy() { project_attachment_cell(photos); }
};

inline void from_json(const json& record, CopyProbeModel& m) {
    if (record.contains("id")) {
        m.id = record.at("id").get<std::string>();
    }
    if (record.contains("createdTime")) {
        m.created_time = record.at("createdTime").get<DateTime>();
    }
    const json fields = record.contains("fields") ? record.at("fields") : json::object();
    m.name = read_field<std::string>(fields, "fldName");
    m.tags = read_field<std::vector<std::string>>(fields, "fldTags");
    m.links = read_field<std::vector<std::string>>(fields, "fldLinks");
    m.photos = read_field<std::vector<AirtableAttachment>>(fields, "fldPhotos");
    m.auto_number = read_field<MaybeSpecialOrError<int64_t>>(fields, "fldAuto");
    m.formula_id = read_field<std::string>(fields, "fldFormula");
    m.photo_lookup = read_field<std::vector<AirtableAttachment>>(fields, "fldLookup");
}

} // namespace myairtable

namespace {

// A record as the SERVER hands it back: attachments carry the read-only metadata
// (att-prefixed id, size, type, thumbnails) that create rejects.
constexpr const char* kEnvelope = R"({
  "id": "recSource001",
  "createdTime": "2024-01-15T10:30:00.000Z",
  "fields": {
    "fldName": "original",
    "fldTags": ["a", "b"],
    "fldLinks": ["recLinkedA", "recLinkedB"],
    "fldPhotos": [
      {"id": "attServerSide01", "url": "https://example.com/a.png", "filename": "a.png",
       "size": 1234, "type": "image/png",
       "thumbnails": {"small": {"url": "https://example.com/a-s.png", "width": 10, "height": 10}}}
    ],
    "fldAuto": 7,
    "fldFormula": "recSource001",
    "fldLookup": [
      {"id": "attLookedUp01", "url": "https://example.com/b.png", "filename": "b.png",
       "size": 99, "type": "image/png"}
    ]
  }
})";

std::shared_ptr<AirtableClient> fast_client(FakeTransport& transport) {
    return std::make_shared<AirtableClient>("app1", "key1", transport.fn(), 0.0, 0.0);
}

// One server-decoded model, with a client attached and a clean snapshot, exactly as a
// table hands it out. Nothing after this point is allowed to hit the transport.
CopyProbeModel decoded(FakeTransport& transport) {
    transport.respond(200, kEnvelope);
    return OrmTable<CopyProbeModel>(fast_client(transport)).get_one("recSource001");
}

} // namespace

TEST_CASE("copy: clears the record identity", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);
    REQUIRE_FALSE(source.is_new());

    const CopyProbeModel copied = source.copy();

    REQUIRE_FALSE(copied.id.has_value());
    REQUIRE_FALSE(copied.created_time.has_value());
    REQUIRE(copied.is_new());
    // require_id() is the guard every write path goes through; on a copy it must refuse.
    REQUIRE_THROWS_AS(copied.require_id(), ApiError);
    // save() would PATCH the source row -- the whole failure this detach prevents.
    REQUIRE_THROWS_AS(copied.save(), ApiError);
    REQUIRE_THROWS_AS(copied.fetch(), ApiError);
    REQUIRE_THROWS_AS(copied.remove(), ApiError);
}

TEST_CASE("copy: resets the snapshot so the copy reads fully dirty", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);
    // Table-decoded models are snapshotted, so the source is clean.
    REQUIRE(source.snapshot_.is_object());
    REQUIRE(source.dirty_fields().empty());

    const CopyProbeModel copied = source.copy();

    // JSON null, NOT an empty object: dirty_fields() short-circuits on !is_object().
    REQUIRE(copied.snapshot_.is_null());
    const json dirty = copied.dirty_fields();
    REQUIRE(dirty.contains("fldName"));
    REQUIRE(dirty.contains("fldTags"));
    REQUIRE(dirty.contains("fldLinks"));
    REQUIRE(dirty.contains("fldPhotos"));
    // A carried snapshot would make this empty -- the {"fields":{}} blank-record trap.
    REQUIRE(dirty.size() == 4);
}

TEST_CASE("copy: keeps the client handle", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);

    const CopyProbeModel copied = source.copy();

    REQUIRE(copied.client_ != nullptr);
    REQUIRE(copied.client_ == source.client_);
    REQUIRE_NOTHROW(copied.require_client());
}

TEST_CASE("copy: a hand-built model copies without a client", "[model][copy]") {
    // copy() must not require attachment -- it is a pure value operation.
    const auto source = CopyProbeModel{.name = "local"};
    const CopyProbeModel copied = source.copy();

    REQUIRE(copied.name == "local");
    REQUIRE(copied.client_ == nullptr);
    REQUIRE(copied.is_new());
    REQUIRE_THROWS_AS(copied.require_client(), ApiError);
}

TEST_CASE("copy: carries computed values but keeps them off the create payload", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);

    const CopyProbeModel copied = source.copy();

    // Readable on the copy, so it renders like its source...
    REQUIRE(copied.auto_number.has_value());
    REQUIRE(copied.auto_number->value() == 7);
    REQUIRE(copied.formula_id == "recSource001"); // stale by design: the SOURCE's id
    REQUIRE(copied.to_record().contains("fldAuto"));
    REQUIRE(copied.to_record().contains("fldFormula"));

    // ...and absent from what create_one() POSTs, which walks writable fields only.
    const json payload = copied.to_create_fields();
    REQUIRE_FALSE(payload.contains("fldAuto"));
    REQUIRE_FALSE(payload.contains("fldFormula"));
    REQUIRE_FALSE(payload.contains("fldLookup"));
    REQUIRE(payload.contains("fldName"));
}

TEST_CASE("copy: projects writable attachments to {url, filename}", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);

    const CopyProbeModel copied = source.copy();

    REQUIRE(copied.photos.has_value());
    REQUIRE(copied.photos->size() == 1);
    const AirtableAttachment& photo = copied.photos->front();
    REQUIRE(photo.url == "https://example.com/a.png");
    REQUIRE(photo.filename == "a.png");
    // id is what create rejects (INVALID_ATTACHMENT_OBJECT); the rest are read-only echoes.
    REQUIRE_FALSE(photo.id.has_value());
    REQUIRE_FALSE(photo.size.has_value());
    REQUIRE_FALSE(photo.type.has_value());
    REQUIRE_FALSE(photo.thumbnails.has_value());

    // And the serialized create body carries only those two keys.
    const json cell = copied.to_create_fields().at("fldPhotos");
    REQUIRE(cell.size() == 1);
    REQUIRE(cell.at(0) == json{{"url", "https://example.com/a.png"}, {"filename", "a.png"}});
}

TEST_CASE("copy: leaves COMPUTED attachment-shaped cells whole", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);

    const CopyProbeModel copied = source.copy();

    // A lookup can hold the identical shape. It never reaches a create body, so
    // stripping its metadata would lose fidelity for nothing.
    REQUIRE(copied.photo_lookup.has_value());
    const AirtableAttachment& looked_up = copied.photo_lookup->front();
    REQUIRE(looked_up.id == "attLookedUp01");
    REQUIRE(looked_up.size == 99);
    REQUIRE(looked_up.type == "image/png");
}

TEST_CASE("copy: absent attachment cells stay absent", "[model][copy]") {
    // nullopt means "field not set", not "empty" -- projection must not materialize it.
    const auto source = CopyProbeModel{.name = "no photos"};
    const CopyProbeModel copied = source.copy();

    REQUIRE_FALSE(copied.photos.has_value());
    REQUIRE_FALSE(copied.to_create_fields().contains("fldPhotos"));
}

TEST_CASE("copy: shares no mutable state with its source", "[model][copy]") {
    FakeTransport transport;
    CopyProbeModel source = decoded(transport);

    CopyProbeModel copied = source.copy();

    copied.name = "mutated";
    copied.tags->push_back("c");
    copied.links->clear();
    copied.photos->push_back(AirtableAttachment{.url = "https://example.com/new.png"});
    copied.snapshot_ = json::object();

    REQUIRE(source.name == "original");
    REQUIRE(source.tags == std::vector<std::string>{"a", "b"});
    REQUIRE(source.links == std::vector<std::string>{"recLinkedA", "recLinkedB"});
    REQUIRE(source.photos->size() == 1);
    REQUIRE(source.snapshot_.is_object());
    REQUIRE(source.snapshot_.contains("fldName"));
}

TEST_CASE("copy: leaves the source completely untouched", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);
    const json record_before = source.to_record();
    const json payload_before = source.to_create_fields();
    const json snapshot_before = source.snapshot_;

    (void)source.copy();

    REQUIRE(source.id == "recSource001");
    REQUIRE(source.created_time.has_value());
    REQUIRE(source.snapshot_ == snapshot_before);
    REQUIRE(source.to_record() == record_before);
    REQUIRE(source.to_create_fields() == payload_before);
    // Notably the source's attachment metadata survives -- projection is copy-local.
    REQUIRE(source.photos->front().id == "attServerSide01");
    // Linked records are copied as-is; the source's own links are never rewritten.
    REQUIRE(source.links == std::vector<std::string>{"recLinkedA", "recLinkedB"});
}

TEST_CASE("copy: performs no I/O", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);
    const size_t calls_after_decode = transport.calls();

    const CopyProbeModel a = source.copy();
    const CopyProbeModel b = a.copy();
    (void)b;

    REQUIRE(transport.calls() == calls_after_decode);
}

TEST_CASE("copy: is idempotent -- copying a copy stays detached", "[model][copy]") {
    FakeTransport transport;
    const CopyProbeModel source = decoded(transport);

    const CopyProbeModel twice = source.copy().copy();

    REQUIRE(twice.is_new());
    REQUIRE(twice.snapshot_.is_null());
    REQUIRE(twice.client_ == source.client_);
    REQUIRE(twice.name == "original");
    REQUIRE_FALSE(twice.photos->front().id.has_value());
}
