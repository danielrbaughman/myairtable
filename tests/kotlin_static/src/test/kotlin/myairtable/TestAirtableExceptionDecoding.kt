package myairtable

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * K2.1 — Decode real-world Airtable error response bodies into AirtableException
 * via the internal AirtableErrorEnvelope. Structured form (default) and legacy
 * string form both supported. Parity: Swift TestAirtableErrorDecoding.
 */
class TestAirtableExceptionDecoding {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun structuredErrorDecodesToApiWithTypeAndMessage() {
        val body = """{ "error": { "type": "NOT_FOUND", "message": "Record not found" } }"""
        val err = json.decodeFromString<AirtableErrorEnvelope>(body).toAirtableException()
        assertEquals(AirtableException.Api("NOT_FOUND", "Record not found"), err)
    }

    @Test
    fun structuredErrorWithMissingMessageDecodesToEmptyString() {
        val body = """{ "error": { "type": "INVALID_REQUEST" } }"""
        val err = json.decodeFromString<AirtableErrorEnvelope>(body).toAirtableException()
        assertEquals(AirtableException.Api("INVALID_REQUEST", ""), err)
    }

    @Test
    fun legacyStringFormErrorDecodesToApiWithCodeUnknown() {
        val body = """{ "error": "AUTHENTICATION_REQUIRED" }"""
        val err = json.decodeFromString<AirtableErrorEnvelope>(body).toAirtableException()
        assertEquals(AirtableException.Api("UNKNOWN", "AUTHENTICATION_REQUIRED"), err)
    }

    @Test
    fun commonAirtableErrorTypesDecodeCleanly() {
        val cases =
            listOf(
                "NOT_FOUND" to "Could not find record",
                "INVALID_REQUEST_UNKNOWN_FIELD" to "Unknown field name",
                "INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND" to "Permission denied",
                "AUTHENTICATION_REQUIRED" to "Not authenticated",
                "TABLE_NOT_FOUND" to "Could not find table",
            )
        for ((code, message) in cases) {
            val body = """{ "error": { "type": "$code", "message": "$message" } }"""
            val err = json.decodeFromString<AirtableErrorEnvelope>(body).toAirtableException()
            assertEquals(AirtableException.Api(code, message), err)
        }
    }

    @Test
    fun malformedBodyThrowsADecodingError() {
        assertFailsWith<Exception> {
            json.decodeFromString<AirtableErrorEnvelope>("""{ "nope": true }""")
        }
    }

    @Test
    fun exceptionMessageIsHumanReadable() {
        val err = AirtableException.Api("NOT_FOUND", "Could not find record")
        assertTrue(err.message!!.contains("NOT_FOUND"))
        assertTrue(err.message!!.contains("Could not find record"))
    }

    @Test
    fun rateLimitedWithRetryAfterFormatsCorrectly() {
        val err = AirtableException.RateLimited(retryAfterSeconds = 30.0)
        assertTrue(err.message!!.contains("30"))
    }

    @Test
    fun httpWithoutBodyOmitsBodyText() {
        val err = AirtableException.Http(statusCode = 500, body = null)
        assertTrue(err.message!!.contains("500"))
        assertEquals("AirtableException.Http(500)", err.message)
    }

    @Test
    fun equalsReflexive() {
        assertEquals(AirtableException.Api("X", "y"), AirtableException.Api("X", "y"))
        assertEquals(AirtableException.InvalidUrl(), AirtableException.InvalidUrl())
        assertEquals(AirtableException.MissingCredentials(), AirtableException.MissingCredentials())
        assertEquals(AirtableException.RateLimited(1.5), AirtableException.RateLimited(1.5))
    }

    @Test
    fun equalsDifferentValuesAreNotEqual() {
        assertNotEquals<AirtableException>(AirtableException.InvalidUrl(), AirtableException.MissingCredentials())
        assertNotEquals(AirtableException.Http(404, null), AirtableException.Http(500, null))
        assertNotEquals(AirtableException.RateLimited(1.0), AirtableException.RateLimited(null))
    }
}
