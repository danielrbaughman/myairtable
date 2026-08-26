package myairtable

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Airtable's create endpoint is a strict whitelist for attachments: only {url} /
 * {url, filename}. Verified against the live API — an id, alone or echoed alongside url,
 * fails with INVALID_ATTACHMENT_OBJECT.
 */
class TestDuplicatePayload {
    private fun serverAttachmentCell(): JsonElement =
        JsonArray(
            listOf(
                JsonObject(
                    mapOf(
                        "id" to JsonPrimitive("attServerSide0001"),
                        "url" to JsonPrimitive("https://example.com/a.png"),
                        "filename" to JsonPrimitive("a.png"),
                        "size" to JsonPrimitive(1234),
                        "type" to JsonPrimitive("image/png"),
                        "width" to JsonPrimitive(10),
                    ),
                ),
            ),
        )

    @Test
    fun stripsReadOnlyMetadataThatCreateRejects() {
        val projected = projectAttachmentsForCreate(mapOf("fldAtt" to serverAttachmentCell()))
        val items = projected["fldAtt"] as JsonArray
        assertEquals(1, items.size)
        val only = items[0] as JsonObject
        assertEquals(JsonPrimitive("https://example.com/a.png"), only["url"])
        assertEquals(JsonPrimitive("a.png"), only["filename"])
        assertFalse(only.containsKey("id"), "id must be dropped: create rejects it")
        for (key in listOf("size", "type", "width")) {
            assertFalse(only.containsKey(key), "read-only key $key must be dropped")
        }
    }

    @Test
    fun passesThroughCallerBuiltAttachments() {
        val fields = mapOf("fldAtt" to JsonArray(listOf(JsonObject(mapOf("url" to JsonPrimitive("u"))))))
        assertEquals(fields, projectAttachmentsForCreate(fields))
    }

    @Test
    fun leavesOtherCellTypesAlone() {
        // Linked records, collaborators and plain arrays must not be mistaken for attachments.
        val fields =
            mapOf(
                "fldLink" to JsonArray(listOf(JsonPrimitive("rec1"), JsonPrimitive("rec2"))),
                "fldUser" to JsonObject(mapOf("id" to JsonPrimitive("usrX"))),
                "fldUsers" to JsonArray(listOf(JsonObject(mapOf("id" to JsonPrimitive("usrX"))))),
                "fldEmpty" to JsonArray(emptyList()),
                "fldText" to JsonPrimitive("https://example.com"),
            )
        assertEquals(fields, projectAttachmentsForCreate(fields))
    }

    @Test
    fun doesNotMutateCallerFields() {
        val cell = serverAttachmentCell()
        val fields = mapOf("fldAtt" to cell)
        projectAttachmentsForCreate(fields)
        assertTrue((((fields["fldAtt"] as JsonArray)[0]) as JsonObject).containsKey("id"))
    }
}
