package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.3 verify-first spike, kept as a regression test: Airtable's server decodes a
 * raw {@code +} in query values as a space, corrupting formulas like {@code LEN({f})+1}. The Java
 * client uses {@link java.net.URLEncoder} form encoding, which percent-encodes {@code +} as {@code
 * %2B} (and encodes spaces as {@code +}, which Airtable decodes back to spaces) — these tests pin
 * that behavior. Offline: only builds URLs, no requests are sent.
 */
class TestClientUrlEncoding {

  private final AirtableClient client = new AirtableClient("appBASE", "key");

  @Test
  void plusInFormulaIsPercentEncoded() {
    URI url =
        client.tableUrl(
            "tblX",
            new AirtableQuery()
                .withFormula("LEN({f})+1 = 2")
                .withReturnFieldsByFieldId(false)
                .toParameters());
    String query = url.getRawQuery();
    assertTrue(query.contains("%2B"), "raw + must be percent-encoded, got: " + query);
    // No RAW plus may remain except as the space encoding.
    assertFalse(query.contains("})+1"), "raw + leaked into query: " + query);
  }

  @Test
  void urlPathContainsBaseAndTable() {
    URI url = client.tableUrl("tblX", List.of());
    assertEquals("/v0/appBASE/tblX", url.getRawPath());
  }

  @Test
  void recordUrlAppendsRecordId() {
    URI url = client.recordUrl("tblX", "recABC", List.of());
    assertEquals("/v0/appBASE/tblX/recABC", url.getRawPath());
  }

  @Test
  void deleteRecordsParamsEncodeAsRepeatedRecordsArray() {
    URI url =
        client.tableUrl(
            "tblX",
            List.of(
                new AirtableQuery.Param("records[]", "rec1"),
                new AirtableQuery.Param("records[]", "rec2")));
    String query = url.getRawQuery();
    assertTrue(query.contains("records%5B%5D=rec1") || query.contains("records[]=rec1"), query);
    assertTrue(query.contains("rec2"));
  }
}
