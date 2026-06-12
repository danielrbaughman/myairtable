package myairtable

import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.seconds

/**
 * K2.2 — Computed-field error / special-value decoding. Parity with Swift
 * TestSpecialErrorDecoding / Rust test_special_error_deser.
 *
 * Airtable returns `{"specialValue": "NaN"}` / `{"error": "#ERROR!"}` objects
 * for formula / rollup / lookup fields whose computation is non-finite or
 * fails. Object forms must decode; array forms must NOT (regression: lookup
 * arrays like ["Lab Name"] must never collapse into Special/Error).
 */
class TestSpecialErrorDecoding {
    private val json = Json { ignoreUnknownKeys = true }

    private inline fun <reified T> decode(raw: String): T = json.decodeFromString<T>(raw)

    // region SpecialNumber / ErrorValue

    @Test
    fun specialNumberAcceptsObjectForm() {
        assertEquals("NaN", decode<SpecialNumber>("""{"specialValue":"NaN"}""").specialValue)
        assertEquals("Infinity", decode<SpecialNumber>("""{"specialValue":"Infinity"}""").specialValue)
    }

    @Test
    fun specialNumberRejectsArrayForm() {
        assertFailsWith<Exception> { decode<SpecialNumber>("""["NaN"]""") }
    }

    @Test
    fun errorValueAcceptsObjectForm() {
        assertEquals("#ERROR!", decode<ErrorValue>("""{"error":"#ERROR!"}""").error)
    }

    @Test
    fun errorValueRejectsArrayForm() {
        assertFailsWith<Exception> { decode<ErrorValue>("""["#ERROR!"]""") }
    }

    // endregion

    // region MaybeSpecialOrError

    @Test
    fun maybeDecodesValue() {
        assertEquals(MaybeSpecialOrError.Value(42.5), decode<MaybeSpecialOrError<Double>>("42.5"))
    }

    @Test
    fun maybeDecodesSpecial() {
        assertEquals(
            MaybeSpecialOrError.Special<Double>(SpecialNumber("NaN")),
            decode<MaybeSpecialOrError<Double>>("""{"specialValue":"NaN"}"""),
        )
    }

    @Test
    fun maybeDecodesError() {
        assertEquals(
            MaybeSpecialOrError.Error<Double>(ErrorValue("#ERROR!")),
            decode<MaybeSpecialOrError<Double>>("""{"error":"#ERROR!"}"""),
        )
    }

    @Test
    fun maybeStringParsesPlainString() {
        assertEquals("Stukenholtz", decode<MaybeSpecialOrError<String>>("\"Stukenholtz\"").valueOrNull)
    }

    @Test
    fun maybeStringRejectsLookupArray() {
        // Regression: ["Stukenholtz"] must not accidentally decode as Special or Value.
        assertFailsWith<Exception> { decode<MaybeSpecialOrError<String>>("""["Stukenholtz"]""") }
    }

    @Test
    fun maybeHelpers() {
        val v: MaybeSpecialOrError<Int> = MaybeSpecialOrError.Value(42)
        assertTrue(v.isValue)
        assertEquals(42, v.valueOrNull)
        assertFalse(v.isSpecial)
        assertFalse(v.isError)

        val e: MaybeSpecialOrError<Int> = MaybeSpecialOrError.Error(ErrorValue("#ERROR!"))
        assertTrue(e.isError)
        assertNull(e.valueOrNull)
        assertEquals("#ERROR!", e.errorOrNull?.error)

        val s: MaybeSpecialOrError<Int> = MaybeSpecialOrError.Special(SpecialNumber("NaN"))
        assertTrue(s.isSpecial)
        assertEquals("NaN", s.specialOrNull?.specialValue)
    }

    // endregion

    // region VecOrValue

    @Test
    fun vecOrValueSingle() {
        val v = decode<VecOrValue<MaybeSpecialOrError<String>>>("\"hello\"")
        assertEquals("hello", v.single?.valueOrNull)
    }

    @Test
    fun vecOrValueMultiple() {
        val v = decode<VecOrValue<MaybeSpecialOrError<String>>>("""["Stukenholtz Laboratory Inc"]""")
        assertEquals(1, v.multiple?.size)
        assertEquals(listOf("Stukenholtz Laboratory Inc"), v.values.mapNotNull { it.valueOrNull })
    }

    @Test
    fun vecOrValueNullableItemsPreserved() {
        val v = decode<VecOrValue<MaybeSpecialOrError<String>>>("""["a", null, "b"]""")
        val items = v.multiple ?: error("expected multiple")
        assertEquals(3, items.size)
        assertNull(items[1])
    }

    @Test
    fun vecOrValueAllNulls() {
        val v = decode<VecOrValue<MaybeSpecialOrError<String>>>("[null, null]")
        assertEquals(2, v.multiple?.size)
        assertTrue(v.values.isEmpty())
    }

    @Test
    fun vecOrValueEmpty() {
        assertEquals(true, decode<VecOrValue<MaybeSpecialOrError<String>>>("[]").multiple?.isEmpty())
    }

    @Test
    fun vecOrValueSpecialNumberObject() {
        val v = decode<VecOrValue<MaybeSpecialOrError<Double>>>("""{"specialValue":"NaN"}""")
        assertEquals("NaN", v.single?.specialOrNull?.specialValue)
    }

    @Test
    fun vecOrValueErrorValueObject() {
        val v = decode<VecOrValue<MaybeSpecialOrError<Double>>>("""{"error":"#ERROR!"}""")
        assertEquals("#ERROR!", v.single?.errorOrNull?.error)
    }

    @Test
    fun vecOrValueMixedArray() {
        val v = decode<VecOrValue<MaybeSpecialOrError<Int>>>("""[1, {"specialValue":"NaN"}, {"error":"#ERROR!"}, null]""")
        val items = v.multiple ?: error("expected multiple")
        assertEquals(4, items.size)
        assertEquals(1, items[0]?.valueOrNull)
        assertEquals("NaN", items[1]?.specialOrNull?.specialValue)
        assertEquals("#ERROR!", items[2]?.errorOrNull?.error)
        assertNull(items[3])
    }

    // endregion

    // region Round-trips

    @Test
    fun specialNumberRoundTrip() {
        val original = SpecialNumber("NaN")
        val encoded = json.encodeToString(SpecialNumber.serializer(), original)
        assertEquals("""{"specialValue":"NaN"}""", encoded)
        assertEquals(original, decode<SpecialNumber>(encoded))
    }

    @Test
    fun maybeEncodesUntagged() {
        val v: MaybeSpecialOrError<Int> = MaybeSpecialOrError.Value(7)
        assertEquals("7", json.encodeToString(MaybeSpecialOrErrorSerializer(Int.serializer()), v))
        val e: MaybeSpecialOrError<Int> = MaybeSpecialOrError.Error(ErrorValue("#ERROR!"))
        assertEquals("""{"error":"#ERROR!"}""", json.encodeToString(MaybeSpecialOrErrorSerializer(Int.serializer()), e))
    }

    @Test
    fun vecOrValueSerializesMultipleWithNulls() {
        val v: VecOrValue<MaybeSpecialOrError<String>> =
            VecOrValue.Multiple(listOf<MaybeSpecialOrError<String>?>(MaybeSpecialOrError.Value("a"), null))
        val serializer = VecOrValueSerializer(MaybeSpecialOrErrorSerializer(String.serializer()))
        assertEquals("""["a",null]""", json.encodeToString(serializer, v))
    }

    // endregion

    // region Duration serializer (wire = seconds)

    @Test
    fun durationDecodesWireSeconds() {
        val box = json.decodeFromString<Map<String, Double>>("""{"d": 3600.0}""")
        assertEquals(3600.0, box["d"])
        assertEquals(
            1.seconds,
            json.decodeFromString(AirtableDurationSerializer, "1"),
        )
        assertEquals(
            3600.seconds,
            json.decodeFromString(AirtableDurationSerializer, "3600"),
        )
    }

    @Test
    fun durationEncodesWireSeconds() {
        assertEquals("90.0", json.encodeToString(AirtableDurationSerializer, 90.seconds))
    }

    // endregion
}

/**
 * myairtable-dmiw — sentinel objects with sibling keys still decode as
 * Special/Error (containment match, mirroring Swift's lenient Codable).
 */
class TestSentinelSiblingKeys {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun specialWithSiblingKeyStillDecodesAsSpecial() {
        val v = json.decodeFromString<MaybeSpecialOrError<Double>>("""{"specialValue":"NaN","future":1}""")
        assertEquals("NaN", v.specialOrNull?.specialValue)
    }

    @Test
    fun errorWithSiblingKeyStillDecodesAsError() {
        val v = json.decodeFromString<MaybeSpecialOrError<Double>>("""{"error":"#ERROR!","detail":"x"}""")
        assertEquals("#ERROR!", v.errorOrNull?.error)
    }
}
