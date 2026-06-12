package myairtable

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * K2.5 — Fields dual ID/name lookup: ID-first, name fallback via nameToId.
 * Parity: Swift TestFieldsDualAccess.
 */
class TestFieldsDualAccess {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeFields(): Fields =
        Fields(
            storage = mapOf("fldABC" to JsonPrimitive("hello"), "fldNUM" to JsonPrimitive(42)),
            nameToId = mapOf("Primary Key" to "fldABC", "Amount" to "fldNUM"),
        )

    @Test
    fun idLookupReturnsTheStoredValue() {
        assertEquals(JsonPrimitive("hello"), makeFields()["fldABC"])
    }

    @Test
    fun nameLookupTranslatesToIdAndReturnsTheSameValue() {
        val fields = makeFields()
        assertEquals(fields["fldABC"], fields["Primary Key"])
    }

    @Test
    fun idIsTriedFirstWhenANameAndAnUnrelatedIdCollide() {
        // A key that is BOTH a real ID and someone's name: the ID wins.
        val fields =
            Fields(
                storage = mapOf("fldX" to JsonPrimitive("by-id"), "fldY" to JsonPrimitive("by-name")),
                nameToId = mapOf("fldX" to "fldY"),
            )
        assertEquals(JsonPrimitive("by-id"), fields["fldX"])
    }

    @Test
    fun setByNameStoresUnderTheTranslatedIdNotTheNameItself() {
        val fields = makeFields()
        fields["Primary Key"] = JsonPrimitive("updated")
        assertEquals(JsonPrimitive("updated"), fields["fldABC"])
        assertEquals(listOf("fldABC", "fldNUM").sorted(), fields.ids.sorted())
    }

    @Test
    fun unknownNameWithoutMappingStoresUnderTheRawKey() {
        val fields = makeFields()
        fields["Mystery Field"] = JsonPrimitive(1)
        assertEquals(JsonPrimitive(1), fields["Mystery Field"])
    }

    @Test
    fun nullSetRemovesTheEntry() {
        val fields = makeFields()
        fields["Primary Key"] = null
        assertNull(fields["fldABC"])
        assertEquals(1, fields.count)
    }

    @Test
    fun typedGettersHandleBothIntAndDoubleStorage() {
        val fields =
            Fields(
                storage = mapOf("int" to JsonPrimitive(7), "dbl" to JsonPrimitive(7.9)),
            )
        assertEquals(7L, fields.getLong("int"))
        assertEquals(7L, fields.getLong("dbl"))
        assertEquals(7.0, fields.getDouble("int"))
        assertEquals(7.9, fields.getDouble("dbl"))
        assertNull(fields.getLong("missing"))
    }

    @Test
    fun typedStringGetterRejectsNonStrings() {
        val fields = Fields(storage = mapOf("n" to JsonPrimitive(1), "s" to JsonPrimitive("x")))
        assertNull(fields.getString("n"))
        assertEquals("x", fields.getString("s"))
    }

    @Test
    fun setStringsEncodesAStringArray() {
        val fields = Fields()
        fields.setStrings("fldTags", listOf("a", "b"))
        assertEquals(listOf("a", "b"), fields.getArray("fldTags")?.map { it.jsonPrimitive.content })
    }

    @Test
    fun serializationRoundTripPreservesStorageButDropsNameToId() {
        val original = makeFields()
        val encoded = json.encodeToString(FieldsSerializer, original)
        val decoded = json.decodeFromString(FieldsSerializer, encoded)
        assertEquals(original.toMap(), decoded.toMap())
        assertEquals(emptyMap(), decoded.nameToId)
    }

    @Serializable
    private data class RecordEnvelope(
        val id: String,
        val fields: Fields = Fields(),
    )

    @Test
    fun missingFieldsObjectDecodesWithoutThrowing() {
        // Sparse Airtable responses can omit `fields` entirely.
        val record = json.decodeFromString<RecordEnvelope>("""{"id": "recX"}""")
        assertEquals(0, record.fields.count)
    }
}
