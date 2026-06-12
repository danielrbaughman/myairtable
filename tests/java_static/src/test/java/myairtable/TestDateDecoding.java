package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.2 — Airtable returns date-only fields as "YYYY-MM-DD", which Instant.parse
 * rejects. The AirtableJacksonModule Instant codec must accept all three wire shapes: fractional
 * ISO 8601, plain ISO 8601, and date-only. Parity: Kotlin/Swift TestDateDecoding.
 */
class TestDateDecoding {

  private static final class Box {
    @JsonProperty("date")
    private Instant date;

    public Box() {}
  }

  private static Instant decode(String raw) throws Exception {
    return AirtableJson.MAPPER.readValue("{\"date\": \"" + raw + "\"}", Box.class).date;
  }

  @Test
  void fullIso8601WithFractionalSecondsDecodes() throws Exception {
    assertEquals(1_705_314_600L, decode("2024-01-15T10:30:00.000Z").getEpochSecond());
  }

  @Test
  void iso8601WithoutFractionalSecondsDecodes() throws Exception {
    assertEquals(1_705_314_600L, decode("2024-01-15T10:30:00Z").getEpochSecond());
  }

  @Test
  void dateOnlyDecodesAsUtcMidnight() throws Exception {
    assertEquals(1_705_276_800L, decode("2024-01-15").getEpochSecond());
  }

  @Test
  void garbageDateStringThrows() {
    assertThrows(Exception.class, () -> decode("not-a-date"));
  }

  @Test
  void parserParsesAllSupportedShapes() {
    assertNotNull(AirtableDateParser.parse("2024-01-15T10:30:00.123Z"));
    assertNotNull(AirtableDateParser.parse("2024-01-15T10:30:00+02:00"));
    assertNotNull(AirtableDateParser.parse("2024-01-15"));
    assertNull(AirtableDateParser.parse("01/15/2024"));
    assertNull(AirtableDateParser.parse(""));
  }

  @Test
  void offsetFormNormalizesToUtcInstant() throws Exception {
    assertEquals(decode("2024-01-15T10:30:00Z"), decode("2024-01-15T12:30:00+02:00"));
  }

  @Test
  void encodeProducesIso8601Utc() throws Exception {
    Box box = new Box();
    box.date = Instant.ofEpochSecond(1_705_314_600L);
    assertEquals(
        "{\"date\":\"2024-01-15T10:30:00Z\"}", AirtableJson.MAPPER.writeValueAsString(box));
  }
}
