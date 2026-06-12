package myairtable

import kotlinx.serialization.json.JsonElement
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

// myairtable-yvb3 — Kotlin DX additions:
//   AirtableModel.requireId(), MaybeSpecialOrError<T>?.value,
//   VecOrValue<MaybeSpecialOrError<T>>?.cleanValues, AirtableQuery.withView.

/** Minimal model stub — only the id plumbing matters for requireId(). */
private class DxStubModel : AirtableModel {
    override val tableId: String = "tblStub"
    override var id: RecordId? = null
    override var createdTime: Instant? = null
    override var attachedClient: AirtableClient? = null

    override fun takeSnapshot() {}

    override fun dirtyFields(): Map<String, JsonElement> = emptyMap()

    override fun toRecord(): Map<String, JsonElement> = emptyMap()

    override fun toCreateFields(): Map<String, JsonElement> = emptyMap()
}

class TestRequireId {
    @Test
    fun requireIdReturnsServerAssignedId() {
        val model = DxStubModel()
        model.id = "recABC123"
        assertEquals("recABC123", model.requireId())
    }

    @Test
    fun requireIdThrowsUnsavedModelWhenIdIsNull() {
        val exception = assertFailsWith<AirtableException.Api> { DxStubModel().requireId() }
        assertEquals("UNSAVED_MODEL", exception.code)
    }
}

class TestComputedFieldSugar {
    @Test
    fun valueIsNullOnNullReceiver() {
        val field: MaybeSpecialOrError<Double>? = null
        assertNull(field.value)
    }

    @Test
    fun valueUnwrapsValueVariant() {
        val field: MaybeSpecialOrError<Double>? = MaybeSpecialOrError.Value(2.5)
        assertEquals(2.5, field.value)
    }

    @Test
    fun valueIsNullForSpecialAndErrorVariants() {
        val special: MaybeSpecialOrError<Double>? = MaybeSpecialOrError.Special(SpecialNumber("NaN"))
        val error: MaybeSpecialOrError<Double>? = MaybeSpecialOrError.Error(ErrorValue("#ERROR!"))
        assertNull(special.value)
        assertNull(error.value)
    }

    @Test
    fun cleanValuesIsEmptyOnNullReceiver() {
        val field: VecOrValue<MaybeSpecialOrError<Double>>? = null
        assertTrue(field.cleanValues.isEmpty())
    }

    @Test
    fun cleanValuesUnwrapsSingleShape() {
        val field: VecOrValue<MaybeSpecialOrError<Double>>? = VecOrValue.Single(MaybeSpecialOrError.Value(1.0))
        assertEquals(listOf(1.0), field.cleanValues)
    }

    @Test
    fun cleanValuesSingleSentinelCollapsesToEmpty() {
        val field: VecOrValue<MaybeSpecialOrError<Double>>? = VecOrValue.Single(MaybeSpecialOrError.Error(ErrorValue("#ERROR!")))
        assertTrue(field.cleanValues.isEmpty())
    }

    @Test
    fun cleanValuesDropsNullsSpecialsAndErrorsFromListShape() {
        val field: VecOrValue<MaybeSpecialOrError<Double>>? =
            VecOrValue.Multiple(
                listOf(
                    MaybeSpecialOrError.Value(1.0),
                    null,
                    MaybeSpecialOrError.Special(SpecialNumber("NaN")),
                    MaybeSpecialOrError.Value(2.0),
                    MaybeSpecialOrError.Error(ErrorValue("#ERROR!")),
                ),
            )
        assertEquals(listOf(1.0, 2.0), field.cleanValues)
    }
}

class TestQueryWithView {
    /** Stand-in for a generated `{Table}View` enum constant. */
    private object StubView : AirtableView {
        override val id: String = "viwSTUB12345"
    }

    @Test
    fun withViewEncodesTheViewId() {
        val params = AirtableQuery().withView(StubView).toParameters()
        assertTrue(("view" to "viwSTUB12345") in params)
    }

    @Test
    fun withViewOverridesAnExistingView() {
        val query = AirtableQuery(view = "viwOLD").withView(StubView)
        assertEquals("viwSTUB12345", query.view)
    }
}
