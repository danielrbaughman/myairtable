package myairtable

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Duration.Companion.minutes

/**
 * K2.8 — V/N/S/A/AN/AS/D/isTruthy coercion helpers over JsonElement?.
 * Parity: coercion section of Swift TestAirtableRuntime.
 */
class TestValueCoercion {
    // region N

    @Test
    fun nCoercesNumbersBoolsStrings() {
        assertEquals(0.0, N(null))
        assertEquals(0.0, N(JsonNull))
        assertEquals(1.0, N(JsonPrimitive(true)))
        assertEquals(0.0, N(JsonPrimitive(false)))
        assertEquals(42.0, N(JsonPrimitive(42)))
        assertEquals(2.5, N(JsonPrimitive(2.5)))
        assertEquals(7.0, N(JsonPrimitive(" 7 ")))
        assertEquals(0.0, N(JsonPrimitive("abc")))
        assertEquals(0.0, N(JsonObject(emptyMap())))
    }

    @Test
    fun nTakesFirstElementOfArray() {
        assertEquals(3.0, N(JsonArray(listOf(JsonPrimitive(3), JsonPrimitive(9)))))
        assertEquals(0.0, N(JsonArray(emptyList())))
    }

    // endregion

    // region S

    @Test
    fun sCoercesAllShapes() {
        assertEquals("", S(null))
        assertEquals("", S(JsonNull))
        assertEquals("1", S(JsonPrimitive(true)))
        assertEquals("0", S(JsonPrimitive(false)))
        assertEquals("42", S(JsonPrimitive(42)))
        assertEquals("hello", S(JsonPrimitive("hello")))
        assertEquals("", S(JsonObject(emptyMap())))
    }

    @Test
    fun sStripsTrailingZeroFromWholeFloats() {
        assertEquals("3", S(JsonPrimitive(3.0)))
        assertEquals("2.5", S(JsonPrimitive(2.5)))
    }

    @Test
    fun sTakesFirstElementOfArray() {
        assertEquals("a", S(JsonArray(listOf(JsonPrimitive("a"), JsonPrimitive("b")))))
        assertEquals("", S(JsonArray(emptyList())))
    }

    // endregion

    // region A / AN / AS

    @Test
    fun aFlattensOneLevelAndDropsKotlinNulls() {
        val flat = A(listOf(JsonPrimitive(1), null, JsonArray(listOf(JsonPrimitive(2), JsonPrimitive(3)))))
        assertEquals(listOf(1.0, 2.0, 3.0), flat.map { N(it) })
    }

    @Test
    fun anAndAsCoerce() {
        val args = listOf<kotlinx.serialization.json.JsonElement?>(JsonPrimitive("2"), JsonArray(listOf(JsonPrimitive(3))))
        assertEquals(listOf(2.0, 3.0), AN(args))
        assertEquals(listOf("2", "3"), AS(args))
    }

    // endregion

    // region V

    @Test
    fun vWrapsPrimitivesAndLists() {
        assertEquals(JsonNull, V<String>(null))
        assertEquals(JsonPrimitive("x"), V("x"))
        assertEquals(JsonPrimitive(42L), V(42L))
        assertEquals(JsonPrimitive(2.5), V(2.5))
        assertEquals(JsonPrimitive(true), V(true))
        assertEquals(listOf("a", "b"), V(listOf("a", "b")).jsonArray.map { it.jsonPrimitive.content })
    }

    @Test
    fun vPassesThroughJsonElements() {
        val element = JsonArray(listOf(JsonPrimitive(1)))
        assertEquals(element, V(element))
        assertEquals(JsonNull, V(null as kotlinx.serialization.json.JsonElement?))
    }

    @Test
    fun vEncodesInstantAsIso8601String() {
        val instant = Instant.ofEpochSecond(1_705_314_600L)
        assertEquals(JsonPrimitive("2024-01-15T10:30:00Z"), V(instant))
    }

    @Test
    fun vEncodesDurationAsWireSeconds() {
        assertEquals(JsonPrimitive(90.0), V(1.5.minutes))
    }

    // endregion

    // region D

    @Test
    fun dParsesIsoStringsAndTimestamps() {
        assertEquals(1_705_314_600L, D(JsonPrimitive("2024-01-15T10:30:00.000Z"))?.epochSecond)
        assertEquals(1_705_276_800L, D(JsonPrimitive("2024-01-15"))?.epochSecond)
        assertEquals(1_705_314_600L, D(JsonPrimitive(1_705_314_600))?.epochSecond)
        assertNull(D(JsonPrimitive("garbage")))
        assertNull(D(null))
        assertNull(D(JsonNull))
    }

    // endregion

    // region isTruthy

    @Test
    fun truthinessMatchesAirtableSemantics() {
        assertFalse(isTruthy(null))
        assertFalse(isTruthy(JsonNull))
        assertFalse(isTruthy(JsonPrimitive(0)))
        assertFalse(isTruthy(JsonPrimitive(0.0)))
        assertFalse(isTruthy(JsonPrimitive(Double.NaN)))
        assertFalse(isTruthy(JsonPrimitive("")))
        assertFalse(isTruthy(JsonArray(emptyList())))
        assertFalse(isTruthy(JsonObject(emptyMap())))
        assertFalse(isTruthy(JsonPrimitive(false)))

        assertTrue(isTruthy(JsonPrimitive(true)))
        assertTrue(isTruthy(JsonPrimitive(1)))
        assertTrue(isTruthy(JsonPrimitive(-0.5)))
        assertTrue(isTruthy(JsonPrimitive("x")))
        assertTrue(isTruthy(JsonArray(listOf(JsonNull))))
    }

    // endregion
}

/**
 * myairtable-4929 regression — the emitted equality shapes must EVALUATE
 * correctly: JsonPrimitive content equality made Double "5.0" != Int "5",
 * so =/!= route through N()/S() coercion on both sides.
 */
class TestTranspiledEqualityShapes {
    @Test
    fun numericEqualityShapeIsTrueForWholeNumberFields() {
        // {field} = 5 with field holding 5.0 — the pre-fix shape was constant-false.
        assertTrue(N(V(5.0)) == N(JsonPrimitive(5)))
        assertTrue(N(V(5)) == N(JsonPrimitive(5)))
        assertFalse(N(V(4.0)) == N(JsonPrimitive(5)))
    }

    @Test
    fun numericInequalityShapeIsFalseForEqualValues() {
        assertFalse(N(V(5.0)) != N(JsonPrimitive(5)))
        assertTrue(N(V(4.0)) != N(JsonPrimitive(5)))
    }

    @Test
    fun stringEqualityShapeCoercesBothSides() {
        assertTrue(S(V("hi")) == S(JsonPrimitive("hi")))
        assertTrue(S(V(5.0)) == S(JsonPrimitive(5)), "S() collapses 5.0 to '5'")
        assertFalse(S(V("hi")) == S(JsonPrimitive("ho")))
    }
}

/**
 * myairtable-w3rk regression — V() must resolve Instant nested inside
 * generics via the shared serializersModule instead of silently degrading
 * to JsonNull (which made toRecord() drop computed date fields and formulas
 * referencing them evaluate as BLANK).
 */
class TestVGenericSerializerResolution {
    private val instant = Instant.ofEpochSecond(1_705_314_600L)

    @Test
    fun vResolvesInstantInsideMaybeSpecialOrError() {
        val wrapped: MaybeSpecialOrError<Instant> = MaybeSpecialOrError.Value(instant)
        assertEquals(JsonPrimitive("2024-01-15T10:30:00Z"), V(wrapped))
    }

    @Test
    fun vResolvesInstantInsideVecOrValue() {
        val wrapped: VecOrValue<MaybeSpecialOrError<Instant>> =
            VecOrValue.Single(MaybeSpecialOrError.Value(instant))
        assertEquals(JsonPrimitive("2024-01-15T10:30:00Z"), V(wrapped))
    }

    @Test
    fun vStillDegradesUnserializableTypesToNull() {
        class NotSerializable(
            val x: Int,
        )
        assertEquals(JsonNull, V(NotSerializable(1)))
    }
}
