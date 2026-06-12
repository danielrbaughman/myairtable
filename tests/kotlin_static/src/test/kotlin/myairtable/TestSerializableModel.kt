package myairtable

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * PHASE 0 GATE (K1.13, plan §2.3.1): proves the generated-model serialization design
 * before any generator templating.
 *
 * Design under test:
 * - Mutable @Serializable class with ALL fields in the primary constructor:
 *   computed fields as `val ... = null`, writable fields as `var ... = null`.
 * - @SerialName raw values are Airtable field IDs.
 * - The plugin-generated serializer is used for DECODING server responses
 *   (including via a generic AirtableRecord<T> envelope).
 * - Create/update payloads NEVER use the plugin serializer wholesale: a hand-rolled
 *   writable-only builder emits a JsonObject of writable field IDs.
 * - Dirty tracking via an @Transient snapshot map + diff (mirrors Swift/Rust).
 */

private val json =
    Json {
        ignoreUnknownKeys = true
        encodeDefaults = false
        explicitNulls = false
    }

/** Generic record envelope as returned by the Airtable API. */
@Serializable
private data class PrototypeRecord<T>(
    val id: String,
    val createdTime: String? = null,
    val fields: T,
)

/** Hand-written prototype of what write_models() will emit per table. */
@Serializable
private class PrototypeModel(
    // Computed fields: server-owned, decode-only. `val` makes mutation a compile error.
    @SerialName("fldComputed1") val computedText: String? = null,
    @SerialName("fldComputed2") val autoNumber: Long? = null,
    // Writable fields.
    @SerialName("fldName") var name: String? = null,
    @SerialName("fldQty") var quantity: Double? = null,
    @SerialName("fldTags") var tags: List<String>? = null,
) {
    /** Record id; lives on the envelope, copied over after decode. Never serialized. */
    @Transient var id: String? = null

    /** Snapshot for dirty tracking. Never serialized. */
    @Transient private var snapshot: Map<String, JsonElement> = emptyMap()

    /** Writable fields only, keyed by field ID — the ONLY path to create/update payloads. */
    fun writableFields(): Map<String, JsonElement> =
        buildMap {
            name?.let { put("fldName", JsonPrimitive(it)) }
            quantity?.let { put("fldQty", JsonPrimitive(it)) }
            tags?.let { put("fldTags", json.encodeToJsonElement(it)) }
        }

    fun takeSnapshot() {
        snapshot = writableFields()
    }

    /**
     * Changed-or-cleared writable fields since the last snapshot. Cleared fields are
     * emitted as JsonNull so the API clears them server-side.
     */
    fun dirtyFields(): Map<String, JsonElement> {
        val current = writableFields()
        val dirty = mutableMapOf<String, JsonElement>()
        for ((key, value) in current) {
            if (snapshot[key] != value) dirty[key] = value
        }
        for (key in snapshot.keys) {
            if (key !in current) dirty[key] = JsonNull
        }
        return dirty
    }
}

class TestSerializableModel {
    private val recordJson =
        """
        {
          "id": "recABC123",
          "createdTime": "2024-01-15T10:30:00.000Z",
          "fields": {
            "fldComputed1": "computed value",
            "fldComputed2": 42,
            "fldName": "hello",
            "fldQty": 2.5,
            "fldTags": ["a", "b"],
            "fldUnknownNewField": "ignored"
          }
        }
        """.trimIndent()

    @Test
    fun decodePopulatesComputedValAndWritableVarConstructorParams() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val model = record.fields
        model.id = record.id

        assertEquals("recABC123", model.id)
        assertEquals("computed value", model.computedText)
        assertEquals(42L, model.autoNumber)
        assertEquals("hello", model.name)
        assertEquals(2.5, model.quantity)
        assertEquals(listOf("a", "b"), model.tags)
    }

    @Test
    fun missingFieldsDecodeAsNullSparseResponse() {
        val model = json.decodeFromString<PrototypeModel>("""{"fldName": "only name"}""")
        assertEquals("only name", model.name)
        assertNull(model.computedText)
        assertNull(model.autoNumber)
        assertNull(model.quantity)
        assertNull(model.tags)
    }

    @Test
    fun unknownKeysAreIgnored() {
        val model = json.decodeFromString<PrototypeModel>("""{"fldBrandNew": 1, "fldName": "x"}""")
        assertEquals("x", model.name)
    }

    @Test
    fun constructorWithNullDefaultsAllowsNamedArgsCreation() {
        // The idiomatic creation path the generator must preserve: named args, writable only.
        val model = PrototypeModel(name = "new record", quantity = 1.0)
        assertEquals("new record", model.name)
        assertNull(model.computedText)
    }

    @Test
    fun writableFieldsExcludeComputedFields() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val payload = JsonObject(record.fields.writableFields())

        assertTrue("fldName" in payload)
        assertTrue("fldQty" in payload)
        assertTrue("fldTags" in payload)
        assertFalse("fldComputed1" in payload, "computed fields must never reach a payload")
        assertFalse("fldComputed2" in payload)
    }

    @Test
    fun writableFieldsSkipNulls() {
        val model = PrototypeModel(name = "only name")
        val payload = model.writableFields()
        assertEquals(setOf("fldName"), payload.keys)
    }

    @Test
    fun snapshotIsTransientAndNeverSerialized() {
        val model = PrototypeModel(name = "x")
        model.takeSnapshot()
        val encoded = json.encodeToJsonElement(model).jsonObject
        assertFalse("snapshot" in encoded)
        assertFalse("id" in encoded)
    }

    @Test
    fun dirtyFieldsEmptyAfterSnapshot() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val model = record.fields
        model.takeSnapshot()
        assertTrue(model.dirtyFields().isEmpty())
    }

    @Test
    fun dirtyFieldsContainOnlyMutatedWritables() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val model = record.fields
        model.takeSnapshot()

        model.name = "renamed"
        val dirty = model.dirtyFields()
        assertEquals(setOf("fldName"), dirty.keys)
        assertEquals("renamed", dirty["fldName"]?.jsonPrimitive?.content)
    }

    @Test
    fun clearedFieldBecomesJsonNullForServerSideClear() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val model = record.fields
        model.takeSnapshot()

        model.quantity = null
        val dirty = model.dirtyFields()
        assertEquals(setOf("fldQty"), dirty.keys)
        assertEquals(JsonNull, dirty["fldQty"])
    }

    @Test
    fun roundTripDecodeMutateEncodePayload() {
        val record = json.decodeFromString<PrototypeRecord<PrototypeModel>>(recordJson)
        val model = record.fields
        model.takeSnapshot()
        model.tags = listOf("a", "b", "c")

        val dirty = JsonObject(model.dirtyFields())
        val reparsed = json.decodeFromString<PrototypeModel>(json.encodeToString(JsonObject.serializer(), dirty))
        assertEquals(listOf("a", "b", "c"), reparsed.tags)
        assertNull(reparsed.name, "non-dirty fields are not in the payload")
    }
}
