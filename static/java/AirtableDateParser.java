// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;

/**
 * Parses the three date shapes Airtable sends, in order of likelihood:
 *
 * <ol>
 *   <li>ISO-8601 instant, fractional or plain ({@code 2024-01-15T10:30:00.000Z})
 *   <li>ISO-8601 with offset ({@code 2024-01-15T10:30:00+02:00})
 *   <li>Date-only ({@code 2024-01-15}) — decoded as midnight UTC
 * </ol>
 *
 * <p>Port of the Kotlin {@code AirtableDateParser} (decode order locked by the Swift/Kotlin
 * efforts against live data).
 */
public final class AirtableDateParser {

  private AirtableDateParser() {}

  /**
   * Parse an Airtable date string.
   *
   * @return the parsed {@link Instant}, or {@code null} if no format matches
   */
  public static Instant parse(String s) {
    if (s == null || s.isEmpty()) {
      return null;
    }
    try {
      return Instant.parse(s);
    } catch (DateTimeParseException ignored) {
      // fall through
    }
    try {
      return OffsetDateTime.parse(s).toInstant();
    } catch (DateTimeParseException ignored) {
      // fall through
    }
    try {
      return LocalDate.parse(s).atStartOfDay(ZoneOffset.UTC).toInstant();
    } catch (DateTimeParseException ignored) {
      return null;
    }
  }
}
