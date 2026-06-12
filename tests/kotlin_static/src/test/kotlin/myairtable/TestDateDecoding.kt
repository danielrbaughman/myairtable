package myairtable

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull

/**
 * K2.2 — Airtable returns date-only fields as "YYYY-MM-DD", which Instant.parse
 * rejects. AirtableInstantSerializer must accept all three wire shapes:
 * fractional ISO 8601, plain ISO 8601, and date-only. Parity: Swift TestDateDecoding.
 */
class TestDateDecoding {
    @Serializable
    private data class Box(
        @Serializable(with = AirtableInstantSerializer::class)
        val date: Instant,
    )

    private val json = Json { ignoreUnknownKeys = true }

    private fun decode(raw: String): Instant = json.decodeFromString<Box>("""{"date": "$raw"}""").date

    @Test
    fun fullIso8601WithFractionalSecondsDecodes() {
        assertEquals(1_705_314_600L, decode("2024-01-15T10:30:00.000Z").epochSecond)
    }

    @Test
    fun iso8601WithoutFractionalSecondsDecodes() {
        assertEquals(1_705_314_600L, decode("2024-01-15T10:30:00Z").epochSecond)
    }

    @Test
    fun dateOnlyDecodesAsUtcMidnight() {
        assertEquals(1_705_276_800L, decode("2024-01-15").epochSecond)
    }

    @Test
    fun garbageDateStringThrows() {
        assertFailsWith<Exception> { decode("not-a-date") }
    }

    @Test
    fun parserParsesAllSupportedShapes() {
        assertNotNull(AirtableDateParser.parse("2024-01-15T10:30:00.123Z"))
        assertNotNull(AirtableDateParser.parse("2024-01-15T10:30:00+02:00"))
        assertNotNull(AirtableDateParser.parse("2024-01-15"))
        assertNull(AirtableDateParser.parse("01/15/2024"))
        assertNull(AirtableDateParser.parse(""))
    }

    @Test
    fun offsetFormNormalizesToUtcInstant() {
        assertEquals(decode("2024-01-15T12:30:00+02:00"), decode("2024-01-15T10:30:00Z"))
    }

    @Test
    fun encodeProducesIso8601Utc() {
        val encoded = json.encodeToString(Box.serializer(), Box(Instant.ofEpochSecond(1_705_314_600L)))
        assertEquals("""{"date":"2024-01-15T10:30:00Z"}""", encoded)
    }
}
