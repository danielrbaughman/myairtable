package myairtable

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * K2.3 verify-first spike, kept as a regression test: Airtable's server
 * decodes a raw `+` in query values as a space, corrupting formulas like
 * `LEN({f})+1`. The Swift target needed a manual `%2B` force-encode; Ktor's
 * URLBuilder already percent-encodes `+` (and encodes spaces as `+`, which
 * Airtable decodes back to spaces) — these tests pin that behavior so a Ktor
 * upgrade can't silently regress it.
 */
class TestClientUrlEncoding {
    private val client = AirtableClient(baseId = "appBASE", apiKey = "key")

    @Test
    fun plusInFormulaIsPercentEncoded() {
        val url = client.tableUrl("tblX", AirtableQuery(formula = "LEN({f})+1 = 2", returnFieldsByFieldId = false).toParameters())
        val query = url.encodedQuery
        assertTrue("%2B" in query, "raw + must be percent-encoded, got: $query")
        // No RAW plus may remain except as the space encoding.
        assertFalse("})+1" in query, "raw + leaked into query: $query")
    }

    @Test
    fun urlPathContainsBaseAndTable() {
        val url = client.tableUrl("tblX")
        assertEquals("/v0/appBASE/tblX", url.encodedPath)
    }

    @Test
    fun recordUrlAppendsRecordId() {
        val url = client.recordUrl("tblX", "recABC")
        assertEquals("/v0/appBASE/tblX/recABC", url.encodedPath)
    }

    @Test
    fun deleteRecordsParamsEncodeAsRepeatedRecordsArray() {
        val url = client.tableUrl("tblX", listOf("records[]" to "rec1", "records[]" to "rec2"))
        val query = url.encodedQuery
        assertTrue("records%5B%5D=rec1" in query || "records[]=rec1" in query, query)
        assertTrue("rec2" in query)
    }
}
