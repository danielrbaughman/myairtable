package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Airtable's create endpoint is a strict whitelist for attachments: only {url} / {url, filename}.
 * Verified against the live API — an id, alone or echoed alongside url, fails with
 * INVALID_ATTACHMENT_OBJECT.
 */
class TestDuplicatePayload {

  private static JsonNode parse(String json) {
    try {
      return AirtableJson.MAPPER.readTree(json);
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
  }

  private static final String SERVER_ATTACHMENT =
      "[{\"id\":\"attServerSide1\",\"url\":\"https://example.com/a.png\",\"filename\":\"a.png\","
          + "\"size\":1234,\"type\":\"image/png\",\"thumbnails\":{\"small\":{\"url\":\"x\"}}}]";

  @Test
  void stripsReadOnlyMetadataThatCreateRejects() {
    Map<String, JsonNode> fields = Map.of("fldAtt", parse(SERVER_ATTACHMENT));
    Map<String, JsonNode> projected = AirtableJson.projectAttachmentsForCreate(fields);

    JsonNode items = projected.get("fldAtt");
    assertEquals(1, items.size());
    JsonNode only = items.get(0);
    assertEquals("https://example.com/a.png", only.get("url").asText());
    assertEquals("a.png", only.get("filename").asText());
    assertFalse(only.has("id"), "id must be dropped: create rejects it");
    for (String key : new String[] {"size", "type", "thumbnails"}) {
      assertFalse(only.has(key), "read-only key " + key + " must be dropped");
    }
  }

  @Test
  void passesThroughCallerBuiltAttachments() {
    Map<String, JsonNode> fields = Map.of("fldAtt", parse("[{\"url\":\"u\"}]"));
    assertEquals(
        fields.get("fldAtt"), AirtableJson.projectAttachmentsForCreate(fields).get("fldAtt"));
  }

  @Test
  void leavesOtherCellTypesAlone() {
    // Linked records, collaborators and plain arrays must not be mistaken for attachments.
    Map<String, JsonNode> fields = new LinkedHashMap<>();
    fields.put("fldLink", parse("[\"rec1\",\"rec2\"]"));
    fields.put("fldUser", parse("{\"id\":\"usrX\",\"email\":\"e@x.com\"}"));
    fields.put("fldUsers", parse("[{\"id\":\"usrX\",\"email\":\"e@x.com\"}]"));
    fields.put("fldEmpty", parse("[]"));
    fields.put("fldText", parse("\"https://example.com\""));

    Map<String, JsonNode> projected = AirtableJson.projectAttachmentsForCreate(fields);
    for (Map.Entry<String, JsonNode> entry : fields.entrySet()) {
      assertEquals(entry.getValue(), projected.get(entry.getKey()), entry.getKey());
    }
  }

  @Test
  void doesNotMutateCallerFields() {
    JsonNode attachments = parse(SERVER_ATTACHMENT);
    Map<String, JsonNode> fields = Map.of("fldAtt", attachments);
    AirtableJson.projectAttachmentsForCreate(fields);
    assertTrue(attachments.get(0).has("id"), "caller's node was mutated");
  }
}
