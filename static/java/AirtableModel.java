// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
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
   * Capture the current writable field values as a snapshot. Called after decode and after a
   * successful save so subsequent {@link #dirtyFields()} computes the diff relative to server
   * state.
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
}
