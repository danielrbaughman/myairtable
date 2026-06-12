package myairtable

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * K2.4 — AirtableQuery → list-records parameter encoding for every option.
 * Parity: Swift TestAirtableQueryBuild.
 */
class TestAirtableQueryBuild {
    private fun params(query: AirtableQuery): Map<String, List<String>> = query.toParameters().groupBy({ it.first }, { it.second })

    @Test
    fun defaultQueryOnlyEmitsReturnFieldsByFieldId() {
        assertEquals(listOf("returnFieldsByFieldId" to "true"), AirtableQuery().toParameters())
    }

    @Test
    fun formulaEncodesAsFilterByFormula() {
        val p = params(AirtableQuery(formula = "NOT({Name}=BLANK())"))
        assertEquals(listOf("NOT({Name}=BLANK())"), p["filterByFormula"])
    }

    @Test
    fun emptyFormulaIsOmitted() {
        assertFalse(params(AirtableQuery(formula = "")).containsKey("filterByFormula"))
    }

    @Test
    fun fieldsEncodeAsRepeatedArrayParams() {
        val p = params(AirtableQuery(fields = listOf("fldA", "fldB")))
        assertEquals(listOf("fldA", "fldB"), p["fields[]"])
    }

    @Test
    fun sortEncodesIndexedFieldAndDirection() {
        val q =
            AirtableQuery()
                .withSort("Name")
                .withSort("Age", SortDirection.DESC)
        val p = params(q)
        assertEquals(listOf("Name"), p["sort[0][field]"])
        assertEquals(listOf("asc"), p["sort[0][direction]"])
        assertEquals(listOf("Age"), p["sort[1][field]"])
        assertEquals(listOf("desc"), p["sort[1][direction]"])
    }

    @Test
    fun maxRecordsAndPageSizeEncode() {
        val p = params(AirtableQuery(maxRecords = 10, pageSize = 5))
        assertEquals(listOf("10"), p["maxRecords"])
        assertEquals(listOf("5"), p["pageSize"])
    }

    @Test
    fun viewEncodesAndEmptyViewIsOmitted() {
        assertEquals(listOf("Grid view"), params(AirtableQuery(view = "Grid view"))["view"])
        assertFalse(params(AirtableQuery(view = "")).containsKey("view"))
    }

    @Test
    fun returnFieldsByFieldIdCanBeDisabled() {
        assertFalse(params(AirtableQuery(returnFieldsByFieldId = false)).containsKey("returnFieldsByFieldId"))
    }

    @Test
    fun cellFormatOnlyEmittedWhenNotJson() {
        assertFalse(params(AirtableQuery()).containsKey("cellFormat"))
        assertEquals(listOf("string"), params(AirtableQuery(cellFormat = AirtableQuery.CellFormat.STRING))["cellFormat"])
    }

    @Test
    fun timeZoneAndUserLocaleEncode() {
        val p = params(AirtableQuery(timeZone = "America/Chicago", userLocale = "en-us"))
        assertEquals(listOf("America/Chicago"), p["timeZone"])
        assertEquals(listOf("en-us"), p["userLocale"])
    }

    @Test
    fun combinedQueryEmitsExpectedParameterCount() {
        val q =
            AirtableQuery(
                formula = "X",
                fields = listOf("fldA", "fldB"),
                maxRecords = 10,
                pageSize = 5,
                view = "Grid",
                timeZone = "America/Chicago",
                userLocale = "en-us",
            ).withSort("Name")
        // formula + 2 fields + 2 sort items + maxRecords + pageSize + view +
        // returnFieldsByFieldId + timeZone + userLocale = 11
        assertEquals(11, q.toParameters().size)
    }

    @Test
    fun copySemanticsProduceIndependentQueries() {
        val base = AirtableQuery(formula = "X")
        val modified = base.copy(maxRecords = 1)
        assertTrue(params(base)["maxRecords"] == null)
        assertEquals(listOf("1"), params(modified)["maxRecords"])
        assertEquals(listOf("X"), params(modified)["filterByFormula"])
    }
}
