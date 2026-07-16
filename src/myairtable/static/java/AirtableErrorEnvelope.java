// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

/**
 * Wire-format Airtable error envelope. Matches the shape Airtable returns on non-2xx responses:
 * {@code {"error": {"type": "...", "message": "..."}}} or {@code {"error": "STRING"}} for some
 * legacy endpoints.
 */
record AirtableErrorEnvelope(@JsonProperty("error") JsonNode error) {

  /** Convert to the public exception type. */
  AirtableException toAirtableException() {
    if (error != null && error.isObject()) {
      String type = error.path("type").isTextual() ? error.path("type").asText() : "UNKNOWN";
      String message = error.path("message").isTextual() ? error.path("message").asText() : "";
      return new AirtableException.Api(type, message);
    }
    if (error != null && error.isTextual()) {
      return new AirtableException.Api("UNKNOWN", error.asText());
    }
    return new AirtableException.Api("UNKNOWN", String.valueOf(error));
  }
}
