// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.serializer
import java.time.Instant

/**
 * Implemented by every generated `{Table}Model` class. The generator emits the
 * concrete class with all fields as primary-constructor properties (computed
 * fields as `val`, writable fields as `var`, all defaulting to `null`) plus
 * `@SerialName` field-ID keys, so the kotlinx plugin serializer decodes the
 * record's `fields` object directly (Phase 0 gate, TestSerializableModel.kt).
 *
 * Change detection for partial updates is handled with an explicit snapshot
 * map captured after decode/save — `dirtyFields()` diffs against it.
 */
interface AirtableModel {
    /** Table identity for the model. Generator emits `override val tableId get() = TABLE_ID`. */
    val tableId: String

    /** Airtable record ID. `null` when the model has never been saved. Set by [OrmTable] after decode. */
    var id: RecordId?

    /** Server-assigned creation timestamp. `null` when unsaved. */
    var createdTime: Instant?

    /**
     * Airtable client attached by the table that produced this model. Set by
     * [OrmTable] after a successful decode so [save]/[fetch]/[delete] can call
     * back without the caller threading a table through. Mirrors Rust's
     * `ModelMeta.client` and Python's `_at_client`.
     */
    var attachedClient: AirtableClient?

    /** `true` when the model has no server-assigned ID yet. */
    val isNew: Boolean
        get() = id.isNullOrEmpty()

    /**
     * Capture the current writable field values as a snapshot. Called after
     * decode and after a successful save so subsequent [dirtyFields] computes
     * the diff relative to server state.
     */
    fun takeSnapshot()

    /**
     * Writable fields that changed since the last snapshot, keyed by field ID.
     * Cleared fields appear as JsonNull. Used by [OrmTable.update] to send
     * only what changed.
     */
    fun dirtyFields(): Map<String, JsonElement>

    /** All current non-null field values, keyed by field ID. */
    fun toRecord(): Map<String, JsonElement>

    /**
     * Non-null **writable** field values, keyed by field ID — the only path
     * to create payloads. Computed fields never appear here.
     */
    fun toCreateFields(): Map<String, JsonElement>
}

/**
 * The server-assigned record ID, or an UNSAVED_MODEL error.
 *
 * Replaces the `created.id!!` pattern: every model returned by a table's
 * `create(...)` / `get(...)` carries an ID, so prefer this over the unchecked
 * `!!` — a `null` ID raises a descriptive [AirtableException.Api] instead of a
 * bare [NullPointerException].
 */
fun AirtableModel.requireId(): RecordId = id ?: throw AirtableException.Api("UNSAVED_MODEL", "Model has no server-assigned id yet")

/** The attached client, or a DETACHED_MODEL error. */
fun AirtableModel.requireAttachedClient(): AirtableClient =
    attachedClient
        ?: throw AirtableException.Api(
            "DETACHED_MODEL",
            "Model must be obtained via a table (get / create / upsert) before calling save() / fetch() / delete()",
        )

// Fluent model-side CRUD.
//
// Mirrors the Rust / TS / Py pattern: once a model has been produced by a
// table, it carries that table's client, and save()/fetch()/delete() need no
// extra arguments. `inline reified` resolves the model's plugin serializer at
// the call site — no per-model code generation needed.

/**
 * Persist the model's dirty fields back to Airtable. Requires a saved record
 * (`id != null`) — construct a fresh model and pass it to the table's
 * `create(...)` to insert a brand-new row.
 */
suspend inline fun <reified T : AirtableModel> T.save(): T {
    val client = requireAttachedClient()
    if (id.isNullOrEmpty()) {
        throw AirtableException.Api("UNSAVED_MODEL", "Cannot save a model without an id; use Airtable.<table>.create(...) instead")
    }
    return OrmTable(tableId, serializer<T>(), client).update(this)
}

/** Re-fetch the model from the server. Returns a fresh instance. */
suspend inline fun <reified T : AirtableModel> T.fetch(): T {
    val client = requireAttachedClient()
    val recordId = id
    if (recordId.isNullOrEmpty()) {
        throw AirtableException.Api("UNSAVED_MODEL", "Cannot fetch an unsaved model")
    }
    return OrmTable(tableId, serializer<T>(), client).get(recordId)
}

/** Delete the record referenced by this model's `id`. */
suspend inline fun <reified T : AirtableModel> T.delete() {
    val client = requireAttachedClient()
    val recordId = id
    if (recordId.isNullOrEmpty()) {
        throw AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model")
    }
    OrmTable(tableId, serializer<T>(), client).delete(recordId)
}
