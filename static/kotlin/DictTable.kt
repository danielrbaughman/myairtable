// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable

import io.ktor.http.HttpMethod
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant

/**
 * Raw-dict record accessor for an Airtable table. Forwards all I/O to the
 * [AirtableClient]. Values flow through as [Fields] (dual ID/name-keyed
 * `Map<String, JsonElement>`), bypassing typed `{Table}Model` decoding.
 *
 * Paired with `OrmTable<T>` (K-F4) — both share the same underlying client.
 * Generated `{Table}Table.dict` exposes this accessor.
 */
class DictTable(
    val tableId: String,
    val nameToId: Map<String, String> = emptyMap(),
    private val client: AirtableClient,
) {
    companion object {
        /** Airtable's hard cap for create / update / delete batches. */
        const val BATCH_SIZE: Int = 10

        /**
         * Max in-flight requests for the multi-ID [get] fan-out. Kept just
         * under Airtable's 5-requests-per-second limit so large ID lists
         * don't trigger a synchronized 429 storm.
         */
        const val MAX_CONCURRENT_GETS: Int = 4
    }

    // region Wire envelopes

    @Serializable
    private data class RawRecordEnvelope(
        val id: RecordId,
        @Serializable(with = AirtableInstantSerializer::class)
        val createdTime: Instant? = null,
        val fields: Map<String, JsonElement> = emptyMap(),
    )

    @Serializable
    private data class RawListResponse(
        val records: List<RawRecordEnvelope> = emptyList(),
        val offset: String? = null,
    )

    /** A fully-loaded record: id + createdTime + [Fields]. */
    data class Record(
        val id: RecordId,
        val createdTime: Instant?,
        val fields: Fields,
    )

    // endregion

    private val json = AirtableJson.instance

    private fun toRecord(raw: RawRecordEnvelope): Record =
        Record(
            id = raw.id,
            createdTime = raw.createdTime,
            fields = Fields(raw.fields, nameToId = nameToId),
        )

    private inline fun <T> decoding(block: () -> T): T =
        try {
            block()
        } catch (e: AirtableException) {
            throw e
        } catch (e: Exception) {
            throw AirtableException.Decoding(e)
        }

    // region get (read)

    /** Fetch one record by ID. */
    suspend fun get(recordId: String): Record {
        val payload = client.getRecord(tableId, recordId)
        val envelope = decoding { json.decodeFromString<RawRecordEnvelope>(payload) }
        return toRecord(envelope)
    }

    /**
     * Fetch many records by ID in windows of [MAX_CONCURRENT_GETS]. Chunking
     * bounds both in-flight requests and live coroutines (a semaphore alone
     * would still suspend one coroutine per ID up-front — PR #21 review).
     * Preserves caller-supplied order.
     */
    suspend fun get(recordIds: List<String>): List<Record> {
        if (recordIds.isEmpty()) return emptyList()
        return recordIds.chunked(MAX_CONCURRENT_GETS).flatMap { window ->
            coroutineScope { window.map { id -> async { get(id) } }.awaitAll() }
        }
    }

    /**
     * Fetch records matching the query. Paginates internally using Airtable's
     * `offset` token; returns the full merged list.
     */
    suspend fun get(query: AirtableQuery = AirtableQuery()): List<Record> {
        val collected = mutableListOf<Record>()
        var offset: String? = null
        do {
            val payload =
                if (offset != null) {
                    fetchWithOffset(query, offset)
                } else {
                    client.listRecords(tableId, query)
                }
            val envelope = decoding { json.decodeFromString<RawListResponse>(payload) }
            collected.addAll(envelope.records.map(::toRecord))
            offset = envelope.offset?.takeIf { it.isNotEmpty() }
        } while (offset != null)
        return collected
    }

    /**
     * Refetch with an `offset` continuation token appended to the query
     * parameters. [AirtableQuery] intentionally doesn't model offset (it's a
     * server-driven continuation, not a user-facing parameter), so it is
     * spliced in at the URL layer.
     */
    private suspend fun fetchWithOffset(
        query: AirtableQuery,
        offset: String,
    ): String {
        val params = query.toParameters() + ("offset" to offset)
        return client.send(HttpMethod.Get, client.tableUrl(tableId, params))
    }

    // endregion

    // region create

    /** Create one record and return the populated envelope. */
    suspend fun create(fields: Fields): Record =
        createBatch(listOf(fields)).firstOrNull()
            ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "create returned no records")

    /** Create many records. Chunks into Airtable's 10-per-call batch limit. */
    suspend fun create(fields: List<Fields>): List<Record> = fields.chunked(BATCH_SIZE).flatMap { createBatch(it) }

    private suspend fun createBatch(fields: List<Fields>): List<Record> {
        if (fields.isEmpty()) return emptyList()
        // `typecast` is intentionally omitted — matches the Rust / Py / TS
        // behavior (Airtable defaults it to false).
        val body =
            buildJsonObject {
                put(
                    "records",
                    buildJsonArray {
                        for (f in fields) {
                            add(buildJsonObject { put("fields", JsonObject(f.toMap())) })
                        }
                    },
                )
                // Airtable echoes the inserted records back keyed by field ID,
                // matching `returnFieldsByFieldId=true` on list/get requests.
                put("returnFieldsByFieldId", JsonPrimitive(true))
            }
        val payload = client.createRecords(tableId, body.toString())
        val envelope = decoding { json.decodeFromString<RawListResponse>(payload) }
        return envelope.records.map(::toRecord)
    }

    // endregion

    // region update

    /** Update a single record's field values. */
    suspend fun update(
        recordId: String,
        fields: Fields,
    ): Record =
        updateBatch(listOf(recordId to fields)).firstOrNull()
            ?: throw AirtableException.Api("UNEXPECTED_RESPONSE", "update returned no records")

    /** Update many records. Chunks into Airtable's 10-per-call batch limit. */
    suspend fun update(updates: List<Pair<String, Fields>>): List<Record> = updates.chunked(BATCH_SIZE).flatMap { updateBatch(it) }

    private suspend fun updateBatch(updates: List<Pair<String, Fields>>): List<Record> {
        if (updates.isEmpty()) return emptyList()
        val body =
            buildJsonObject {
                put(
                    "records",
                    buildJsonArray {
                        for ((id, f) in updates) {
                            add(
                                buildJsonObject {
                                    put("id", JsonPrimitive(id))
                                    put("fields", JsonObject(f.toMap()))
                                },
                            )
                        }
                    },
                )
                put("returnFieldsByFieldId", JsonPrimitive(true))
            }
        val payload = client.updateRecords(tableId, body.toString())
        val envelope = decoding { json.decodeFromString<RawListResponse>(payload) }
        return envelope.records.map(::toRecord)
    }

    // endregion

    // region delete

    /** Delete one record by ID. */
    suspend fun delete(recordId: String) {
        client.deleteRecord(tableId, recordId)
    }

    /** Delete many records. Chunks into Airtable's 10-per-call batch limit. */
    suspend fun delete(recordIds: List<String>) {
        for (chunk in recordIds.chunked(BATCH_SIZE)) {
            client.deleteRecords(tableId, chunk)
        }
    }

    // endregion
}
