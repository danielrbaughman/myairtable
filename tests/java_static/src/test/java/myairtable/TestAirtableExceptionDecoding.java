package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.1 — Decode real-world Airtable error response bodies into AirtableException
 * via the internal AirtableErrorEnvelope. Structured form (default) and legacy string form both
 * supported. Parity: Kotlin TestAirtableExceptionDecoding / Swift TestAirtableErrorDecoding.
 */
class TestAirtableExceptionDecoding {

  private static AirtableException decode(String body) throws Exception {
    return AirtableJson.MAPPER.readValue(body, AirtableErrorEnvelope.class).toAirtableException();
  }

  @Test
  void structuredErrorDecodesToApiWithTypeAndMessage() throws Exception {
    String body = "{ \"error\": { \"type\": \"NOT_FOUND\", \"message\": \"Record not found\" } }";
    assertEquals(new AirtableException.Api("NOT_FOUND", "Record not found"), decode(body));
  }

  @Test
  void structuredErrorWithMissingMessageDecodesToEmptyString() throws Exception {
    String body = "{ \"error\": { \"type\": \"INVALID_REQUEST\" } }";
    assertEquals(new AirtableException.Api("INVALID_REQUEST", ""), decode(body));
  }

  @Test
  void legacyStringFormErrorDecodesToApiWithCodeUnknown() throws Exception {
    String body = "{ \"error\": \"AUTHENTICATION_REQUIRED\" }";
    assertEquals(new AirtableException.Api("UNKNOWN", "AUTHENTICATION_REQUIRED"), decode(body));
  }

  @Test
  void commonAirtableErrorTypesDecodeCleanly() throws Exception {
    List<Map.Entry<String, String>> cases =
        List.of(
            Map.entry("NOT_FOUND", "Could not find record"),
            Map.entry("INVALID_REQUEST_UNKNOWN_FIELD", "Unknown field name"),
            Map.entry("INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND", "Permission denied"),
            Map.entry("AUTHENTICATION_REQUIRED", "Not authenticated"),
            Map.entry("TABLE_NOT_FOUND", "Could not find table"));
    for (Map.Entry<String, String> entry : cases) {
      String body =
          "{ \"error\": { \"type\": \""
              + entry.getKey()
              + "\", \"message\": \""
              + entry.getValue()
              + "\" } }";
      assertEquals(new AirtableException.Api(entry.getKey(), entry.getValue()), decode(body));
    }
  }

  @Test
  void malformedBodyDegradesToUnknownApiError() throws Exception {
    // Kotlin's kotlinx serializer THROWS on a body missing the required "error" key.
    // Jackson is configured lenient (unknown properties ignored, record components
    // optional), so the Java envelope degrades to Api("UNKNOWN", ...) instead.
    AirtableException err = decode("{ \"nope\": true }");
    assertInstanceOf(AirtableException.Api.class, err);
    assertEquals("UNKNOWN", ((AirtableException.Api) err).code());
  }

  @Test
  void exceptionMessageIsHumanReadable() {
    AirtableException err = new AirtableException.Api("NOT_FOUND", "Could not find record");
    assertTrue(err.getMessage().contains("NOT_FOUND"));
    assertTrue(err.getMessage().contains("Could not find record"));
  }

  @Test
  void rateLimitedWithRetryAfterFormatsCorrectly() {
    AirtableException err = new AirtableException.RateLimited(30.0);
    assertTrue(err.getMessage().contains("30"));
  }

  @Test
  void httpWithoutBodyOmitsBodyText() {
    AirtableException err = new AirtableException.Http(500, null);
    assertTrue(err.getMessage().contains("500"));
    assertEquals("AirtableException.Http(500)", err.getMessage());
  }

  @Test
  void equalsReflexive() {
    assertEquals(new AirtableException.Api("X", "y"), new AirtableException.Api("X", "y"));
    assertEquals(new AirtableException.InvalidUrl(), new AirtableException.InvalidUrl());
    assertEquals(
        new AirtableException.MissingCredentials(), new AirtableException.MissingCredentials());
    assertEquals(new AirtableException.RateLimited(1.5), new AirtableException.RateLimited(1.5));
  }

  @Test
  void equalsDifferentValuesAreNotEqual() {
    assertNotEquals(new AirtableException.InvalidUrl(), new AirtableException.MissingCredentials());
    assertNotEquals(new AirtableException.Http(404, null), new AirtableException.Http(500, null));
    assertNotEquals(
        new AirtableException.RateLimited(1.0), new AirtableException.RateLimited(null));
  }
}
