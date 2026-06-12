// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import io.ktor.http.HttpMethod
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * Typed record accessor for an Airtable table. Forwards all I/O to the
 * [AirtableClient]; decodes responses into the generated `{Table}Model`
 * classes via the supplied [serializer], attaching the client + taking a
 * snapshot on every decode so model-side `save()`/`dirtyFields()` work.
 */
class OrmTable<T : AirtableModel>(
    val tableId: String,
    private val serializer: KSerializer<T>,
    private val client: AirtableClient,
) {
    companion object {
        /** Airtable's hard cap for create / update / delete batches. */
        const val BATCH_SIZE: Int = 10
    }

    /** Result of [upsert]: the merged model plus whether it was inserted. */
    data class UpsertResult<T>(
        val model: T,
        val wasCreated: Boolean,
    )

    private val json = AirtableJson.instance

    // region Decoding

    private inline fun <R> decoding(block: () -> R): R =
        try {
            block()
        } catch (e: AirtableException) {
            throw e
        } catch (e: Exception) {
            throw AirtableException.Decoding(e)
        }

    /**
     * Decode one `{id, createdTime, fields}` envelope: the plugin serializer
     * handles `fields`; id/createdTime are copied onto the model's transient
     * properties, the client attached, and a snapshot taken.
     */
    private fun decodeEnvelope(element: JsonElement): T =
        decoding {
            val obj = element as? JsonObject ?: error("expected record object, got $element")
            val fieldsElement: JsonElement = obj["fields"] ?: JsonObject(emptyMap())
            val model = json.decodeFromJsonElement(serializer, fieldsElement)
            model.id = (obj["id"] as? JsonPrimitive)?.contentOrNull
            model.createdTime = (obj["createdTime"] as? JsonPrimitive)?.contentOrNull?.let { AirtableDateParser.parse(it) }
            model.attachedClient = client
            model.takeSnapshot()
            model
        }

    private fun decodeRecordPayload(payload: String): T = decodeEnvelope(decoding { json.parseToJsonElement(payload) })

    /** Decode a `{records: [...], offset}` payload. Returns models + offset. */
    private fun decodeListPayload(payload: String): Pair<List<T>, String?> =
        decoding {
            val obj = json.parseToJsonElement(payload) as? JsonObject ?: error("expected list response object")
            val records = (obj["records"] as? JsonArray)?.map { decodeEnvelope(it) } ?: emptyList()
            val offset = (obj["offset"] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotEmpty() }
            records to offset
        }

    // endregion

    // region get (read)

    /** Fetch one record by ID. */
    suspend fun get(recordId: String): T = decodeRecordPayload(client.getRecord(tableId, recordId))

    /** Fetch many records by ID, in order. */
    suspend fun get(recordIds: List<String>): List<T> = recordIds.map { get(it) }

    /**
     * Fetch records matching the query. Paginates internally via the `offset`
     * continuation token; returns the merged list in page-arrival order.
     * Pass `AirtableQuery()` (the default) for all records.
     */
    suspend fun get(query: AirtableQuery = AirtableQuery()): List<T> {
        val collected = mutableListOf<T>()
        var offset: String? = null
        do {
            val payload =
                if (offset != null) {
                    fetchWithOffset(query, offset)
                } else {
                    client.listRecords(tableId, query)
                }
            val (records, nextOffset) = decodeListPayload(payload)
            collected.addAll(records)
            offset = nextOffset
        } while (offset != null)
        return collected
    }

    private suspend fun fetchWithOffset(
        query: AirtableQuery,
        offset: String,
    ): String {
        val params = query.toParameters() + ("offset" to offset)
        return client.send(HttpMethod.Get, client.tableUrl(tableId, params))
    }

    // endregion

    // region create

    /**
     * Create one record. Pass a fresh model built with its constructor (e.g.
     * `PrimaryModel(primaryKey = "x")`); only writable fields are sent.
     */
    suspend fun create(model: T): T =
        createBatch(listOf(model.toCreateFields())).firstOrNull()
            ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "create returned no records")

    /** Create many records. Chunks into Airtable's batch limit (10). */
    suspend fun create(models: List<T>): List<T> = models.map { it.toCreateFields() }.chunked(BATCH_SIZE).flatMap { createBatch(it) }

    private suspend fun createBatch(records: List<Map<String, JsonElement>>): List<T> {
        if (records.isEmpty()) return emptyList()
        // `typecast` is intentionally omitted — Airtable's server-side default
        // is false, matching the Rust / Python / TypeScript targets.
        val body =
            buildJsonObject {
                put(
                    "records",
                    buildJsonArray {
                        for (fields in records) add(buildJsonObject { put("fields", JsonObject(fields)) })
                    },
                )
                put("returnFieldsByFieldId", JsonPrimitive(true))
            }
        val payload = client.createRecords(tableId, body.toString())
        return decodeListPayload(payload).first
    }

    // endregion

    // region update

    /**
     * Update a single model. Diffs against the model's snapshot and sends
     * only fields that changed since the last `takeSnapshot()`.
     */
    suspend fun update(model: T): T =
        update(listOf(model)).firstOrNull()
            ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records")

    /** Update many models (dirty fields only). Chunks into the batch limit. */
    suspend fun update(models: List<T>): List<T> {
        val patches =
            models.map { model ->
                val recordId = model.id
                if (recordId.isNullOrEmpty()) {
                    throw AirtableException.Api("UNSAVED_MODEL", "Cannot update a model without an id")
                }
                recordId to model.dirtyFields()
            }
        return patches.chunked(BATCH_SIZE).flatMap { updateBatch(it) }
    }

    /** Update a record's fields directly by ID (no model required). */
    suspend fun updateFields(
        recordId: String,
        fields: Map<String, JsonElement>,
    ): T =
        updateBatch(listOf(recordId to fields)).firstOrNull()
            ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records")

    private suspend fun updateBatch(patches: List<Pair<String, Map<String, JsonElement>>>): List<T> {
        if (patches.isEmpty()) return emptyList()
        val body =
            buildJsonObject {
                put(
                    "records",
                    buildJsonArray {
                        for ((id, fields) in patches) {
                            add(
                                buildJsonObject {
                                    put("id", JsonPrimitive(id))
                                    put("fields", JsonObject(fields))
                                },
                            )
                        }
                    },
                )
                put("returnFieldsByFieldId", JsonPrimitive(true))
            }
        val payload = client.updateRecords(tableId, body.toString())
        return decodeListPayload(payload).first
    }

    // endregion

    // region upsert

    /**
     * Upsert a record, matching on the supplied field IDs. Returns the merged
     * model plus whether the record was inserted (vs updated).
     */
    suspend fun upsert(
        model: T,
        fieldsToMergeOn: List<String>,
    ): UpsertResult<T> {
        val body =
            buildJsonObject {
                put(
                    "records",
                    buildJsonArray { add(buildJsonObject { put("fields", JsonObject(model.toCreateFields())) }) },
                )
                put("performUpsert", buildJsonObject { put("fieldsToMergeOn", buildJsonArray { fieldsToMergeOn.forEach { add(JsonPrimitive(it)) } }) })
                put("returnFieldsByFieldId", JsonPrimitive(true))
            }
        val payload = client.updateRecords(tableId, body.toString())
        val obj = decoding { json.parseToJsonElement(payload) as JsonObject }
        val records = (obj["records"] as? JsonArray)?.map { decodeEnvelope(it) } ?: emptyList()
        val first =
            records.firstOrNull()
                ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "upsert returned no records")
        val createdIds =
            (obj["createdRecords"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()
        return UpsertResult(model = first, wasCreated = createdIds.contains(first.id ?: ""))
    }

    // endregion

    // region delete

    /** Delete one record by ID. */
    suspend fun delete(recordId: String) {
        client.deleteRecord(tableId, recordId)
    }

    /** Delete many records by ID. Chunks into Airtable's batch limit (10). */
    suspend fun delete(recordIds: List<String>) {
        for (chunk in recordIds.chunked(BATCH_SIZE)) {
            client.deleteRecords(tableId, chunk)
        }
    }

    /** Delete the record referenced by this model's `id`. */
    suspend fun delete(model: T) {
        val id = model.id
        if (id.isNullOrEmpty()) {
            throw AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model")
        }
        delete(id)
    }

    /** Delete many records by passing their models. Chunks by ID. */
    @JvmName("deleteModels")
    suspend fun delete(models: List<T>) {
        val ids =
            models.map { model ->
                model.id.takeUnless { it.isNullOrEmpty() }
                    ?: throw AirtableException.Api("UNSAVED_MODEL", "Cannot delete an unsaved model")
            }
        delete(ids)
    }

    // endregion
}
