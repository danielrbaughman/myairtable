// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Implemented by every generated {@code {Table}Model} class. The generator emits the concrete class
 * with private {@code @JsonProperty} field-ID-keyed fields (computed fields getter-only, writable
 * fields with setters), a public no-arg constructor for Jackson, and a nested {@code Builder} over
 * the writable fields (Phase 0 gate, TestPojoModel.java).
 *
 * <p>Change detection for partial updates is handled with an explicit snapshot map captured after
 * decode/save — {@link #dirtyFields()} diffs against it.
 */
public interface AirtableModel {

  /** Table identity for the model. Generated models return their table's {@code TABLE_ID}. */
  String getTableId();

  /** Airtable record ID. {@code null} when the model has never been saved. Set by OrmTable. */
  String getId();

  void setId(String id);

  /** Server-assigned creation timestamp. {@code null} when unsaved. */
  Instant getCreatedTime();

  void setCreatedTime(Instant createdTime);

  /**
   * Airtable client attached by the table that produced this model. Set by {@link OrmTable} after a
   * successful decode so {@code save()}/{@code fetch()}/{@code delete()} can call back without the
   * caller threading a table through. Mirrors Rust's {@code ModelMeta.client} and Python's {@code
   * _at_client}.
   */
  AirtableClient getAttachedClient();

  void setAttachedClient(AirtableClient client);

  /** {@code true} when the model has no server-assigned ID yet. */
  default boolean isNew() {
    return getId() == null || getId().isEmpty();
  }

  /**
   * Capture the current writable field values as a snapshot, so subsequent {@link #dirtyFields()}
   * computes the diff relative to this point. The table takes a snapshot on every decode (after
   * {@code get}/{@code create}/{@code update}), so a model obtained from a table starts clean.
   *
   * <p>Note: a save returns a FRESH, freshly-snapshotted instance; the model you called {@code
   * save()} on keeps its pre-save snapshot, so re-saving it re-sends the same changes. Use the
   * returned instance for further edits.
   */
  void takeSnapshot();

  /**
   * Writable fields that changed since the last snapshot, keyed by field ID. Cleared fields appear
   * as JSON null. Used by {@link OrmTable#update} to send only what changed.
   */
  Map<String, JsonNode> dirtyFields();

  /** All current non-null field values, keyed by field ID. */
  Map<String, JsonNode> toRecord();

  /**
   * Non-null <b>writable</b> field values, keyed by field ID — the only path to create payloads.
   * Computed fields never appear here.
   */
  Map<String, JsonNode> toCreateFields();

  /**
   * The server-assigned record ID, or an UNSAVED_MODEL error.
   *
   * <p>Every model returned by a table's {@code create(...)} / {@code get(...)} carries an ID, so
   * prefer this over a manual null check — a {@code null} ID raises a descriptive {@link
   * AirtableException.Api} instead of a bare {@link NullPointerException}.
   */
  default String requireId() {
    String id = getId();
    if (id == null || id.isEmpty()) {
      throw new AirtableException.Api("UNSAVED_MODEL", "Model has no server-assigned id yet");
    }
    return id;
  }

  /** The attached client, or a DETACHED_MODEL error. */
  default AirtableClient requireAttachedClient() {
    AirtableClient client = getAttachedClient();
    if (client == null) {
      throw new AirtableException.Api(
          "DETACHED_MODEL",
          "Model must be obtained via a table (get / create / upsert) before calling save() /"
              + " fetch() / delete()");
    }
    return client;
  }

  // ---- copy() support (myairtable-6q37.6) ----------------------------------
  //
  // The generated `{Table}Model.copy()` is emitted per model (java.py) rather than
  // hoisted here as a default method: the only way to seed a COMPUTED field is a
  // direct write to the private POJO field, which is legal from inside the model
  // class and nowhere else (computed fields get no setter and no Builder entry, so
  // "computed fields are server-owned" survives as a public invariant). What CAN live
  // here is the part that is the same for every table — detaching one cell value.
  //
  // Java needs more of that than the Kotlin/Rust ports do. `AirtableAttachment` and
  // `AirtableCollaborator` are deliberately MUTABLE POJOs (write-side ergonomics),
  // Jackson decodes a `List<...>` cell into an `ArrayList`, and a `JsonNode` cell is
  // an `ObjectNode`/`ArrayNode` that can be edited in place. Any of those aliased into
  // a copy would let a mutation of one record be felt by the other.

  /**
   * Reduce one attachment to the {@code {url, filename}} shape Airtable's create endpoint accepts.
   *
   * <p>Applied by {@code copy()} at copy time rather than on the wire, because {@link
   * OrmTable#create(AirtableModel)} does NOT project (only {@code duplicate} does, via {@link
   * AirtableJson#projectAttachmentsForCreate}) — an attachment read back from the server carries
   * {@code id}/{@code size}/{@code type}/{@code thumbnails}, and posting those fails with
   * INVALID_ATTACHMENT_OBJECT. Copying by URL is also what makes the created record own an
   * independent file rather than aliasing the source's.
   *
   * <p>Nulls are dropped on encode, so a caller-built {@code new AirtableAttachment(url)}
   * round-trips unchanged.
   */
  static AirtableAttachment projectAttachmentForCopy(AirtableAttachment attachment) {
    if (attachment == null) {
      return null;
    }
    AirtableAttachment projected = new AirtableAttachment(attachment.getUrl());
    projected.setFilename(attachment.getFilename());
    return projected;
  }

  /**
   * {@link #projectAttachmentForCopy} over a multi-attachment cell. Returns a brand-new list, so it
   * doubles as the defensive re-wrap those cells need.
   *
   * <p>Only WRITABLE cells are projected: a computed lookup can hold the very same attachment
   * shape, is never written back, and stripping its metadata would lose fidelity for nothing —
   * those go through {@link #detachForCopy} instead and keep everything.
   */
  static List<AirtableAttachment> projectAttachmentsForCopy(List<AirtableAttachment> attachments) {
    if (attachments == null) {
      return null;
    }
    List<AirtableAttachment> projected = new ArrayList<>(attachments.size());
    for (AirtableAttachment attachment : attachments) {
      projected.add(projectAttachmentForCopy(attachment));
    }
    return projected;
  }

  /**
   * A deep, value-preserving detach of one cell, for {@code copy()}.
   *
   * <p>Rebuilds every mutable container and POJO the value can reach so the copy shares no state
   * with its source, while carrying the value itself verbatim — including the read-only metadata on
   * a computed attachment-shaped cell, which {@link #projectAttachmentsForCopy} deliberately strips
   * and this deliberately does not.
   *
   * <p>Deliberately NOT a JSON round-trip (the trick the Go port uses): {@code toCreateFields()} is
   * writable-only, so serializing through it would drop exactly the computed values a copy is
   * supposed to carry, and a round-trip through {@code toRecord()} would lose the decoded {@code
   * MaybeSpecialOrError}/{@code VecOrValue} shapes.
   *
   * <p>Everything not matched below is immutable and returned as-is: {@code String}, the boxed
   * numerics, {@code Boolean}, {@code Instant}, {@code Duration}, the generated select-option
   * enums, and the {@code AirtableButton}/{@code AirtableThumbnails}/{@code SpecialNumber}/{@code
   * ErrorValue} records.
   */
  @SuppressWarnings("unchecked")
  static <T> T detachForCopy(T value) {
    Object cell = value;
    return (T)
        switch (cell) {
          case null -> null;
          // Mutable POJOs: a shared instance would let setUrl() on one record be seen by
          // the other. Cloned whole — the projection for writable cells happens elsewhere.
          case AirtableAttachment attachment -> {
            AirtableAttachment copied = new AirtableAttachment(attachment.getUrl());
            copied.setId(attachment.getId());
            copied.setFilename(attachment.getFilename());
            copied.setSize(attachment.getSize());
            copied.setType(attachment.getType());
            copied.setThumbnails(attachment.getThumbnails());
            yield copied;
          }
          case AirtableCollaborator collaborator -> {
            AirtableCollaborator copied = new AirtableCollaborator(collaborator.getId());
            copied.setEmail(collaborator.getEmail());
            copied.setName(collaborator.getName());
            copied.setProfilePicUrl(collaborator.getProfilePicUrl());
            yield copied;
          }
          // An unmodelled cell decodes to an ObjectNode/ArrayNode, which is editable in place.
          case JsonNode node -> node.deepCopy();
          // The computed wrappers are records, but their payload need not be: a lookup of an
          // attachment field decodes to VecOrValue<MaybeSpecialOrError<AirtableAttachment>>.
          case MaybeSpecialOrError.Value<?> wrapped ->
              new MaybeSpecialOrError.Value<>(detachForCopy(wrapped.value()));
          case VecOrValue.Single<?> single ->
              new VecOrValue.Single<>(detachForCopy(single.value()));
          case VecOrValue.Multiple<?> multiple ->
              new VecOrValue.Multiple<>(detachElements(multiple.values()));
          case List<?> list -> detachElements(list);
          default -> cell;
        };
  }

  /**
   * {@link #detachForCopy} over a list, preserving null entries (Airtable emits sparse lookups).
   */
  private static <E> List<E> detachElements(List<E> values) {
    if (values == null) {
      return null;
    }
    List<E> copied = new ArrayList<>(values.size());
    for (E element : values) {
      copied.add(detachForCopy(element));
    }
    return copied;
  }
}
