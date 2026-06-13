package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.IntNode;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.5 — Fields dual ID/name lookup: ID-first, name fallback via nameToId. Parity:
 * Kotlin/Swift TestFieldsDualAccess.
 */
class TestFieldsDualAccess {

  private static Fields makeFields() {
    // IntNode (not LongNode): Jackson node equality is type-strict and a JSON "42"
    // round-trips as IntNode, which serializationRoundTrip asserts against.
    return new Fields(
        Map.of("fldABC", TextNode.valueOf("hello"), "fldNUM", IntNode.valueOf(42)),
        Map.of("Primary Key", "fldABC", "Amount", "fldNUM"));
  }

  @Test
  void idLookupReturnsTheStoredValue() {
    assertEquals(TextNode.valueOf("hello"), makeFields().get("fldABC"));
  }

  @Test
  void nameLookupTranslatesToIdAndReturnsTheSameValue() {
    Fields fields = makeFields();
    assertEquals(fields.get("fldABC"), fields.get("Primary Key"));
  }

  @Test
  void idIsTriedFirstWhenANameAndAnUnrelatedIdCollide() {
    // A key that is BOTH a real ID and someone's name: the ID wins.
    Fields fields =
        new Fields(
            Map.of("fldX", TextNode.valueOf("by-id"), "fldY", TextNode.valueOf("by-name")),
            Map.of("fldX", "fldY"));
    assertEquals(TextNode.valueOf("by-id"), fields.get("fldX"));
  }

  @Test
  void setIsIdFirstWhenANameAndAnUnrelatedIdCollide() {
    // A key that is BOTH a real ID and someone's name: the ID wins on
    // write, mirroring get() (PR #19 review).
    Fields fields =
        new Fields(
            Map.of("fldX", TextNode.valueOf("by-id"), "fldY", TextNode.valueOf("by-name")),
            Map.of("fldX", "fldY"));
    fields.set("fldX", TextNode.valueOf("updated"));
    assertEquals(TextNode.valueOf("updated"), fields.get("fldX"));
    assertEquals(
        TextNode.valueOf("by-name"),
        fields.get("fldY"),
        "the colliding name's target is untouched");
  }

  @Test
  void setTreatsKnownIdAsIdEvenWhenAbsentFromStorage() {
    // Sparse record: the ID isn't in storage yet, but it IS a known field
    // ID (a value in nameToId) — still never name-translated.
    Fields fields = new Fields(Map.of(), Map.of("fldABC", "fldDEF", "Real Name", "fldABC"));
    fields.set("fldABC", LongNode.valueOf(1));
    assertEquals(LongNode.valueOf(1), fields.toMap().get("fldABC"));
    assertNull(fields.toMap().get("fldDEF"));
  }

  @Test
  void setByNameStoresUnderTheTranslatedIdNotTheNameItself() {
    Fields fields = makeFields();
    fields.set("Primary Key", TextNode.valueOf("updated"));
    assertEquals(TextNode.valueOf("updated"), fields.get("fldABC"));
    assertEquals(List.of("fldABC", "fldNUM"), fields.ids().stream().sorted().toList());
  }

  @Test
  void unknownNameWithoutMappingStoresUnderTheRawKey() {
    Fields fields = makeFields();
    fields.set("Mystery Field", LongNode.valueOf(1));
    assertEquals(LongNode.valueOf(1), fields.get("Mystery Field"));
  }

  @Test
  void nullSetRemovesTheEntry() {
    Fields fields = makeFields();
    fields.set("Primary Key", null);
    assertNull(fields.get("fldABC"));
    assertEquals(1, fields.count());
  }

  @Test
  void explicitNullNodeIsStoredAsJsonNullToClearTheFieldServerSide() {
    // JR-H2: a Java null removes, but an explicit NullNode must be STORED — it
    // serializes as JSON `null`, the only way to clear a field via the dict
    // PATCH path. Collapsing NullNode into "remove" omits the key and silently
    // leaves the server value unchanged (Kotlin/Swift/Rust all store it).
    Fields fields = makeFields();
    fields.set("Primary Key", com.fasterxml.jackson.databind.node.NullNode.getInstance());
    assertEquals(2, fields.count(), "the cleared field must remain present (as null)");
    assertTrue(fields.toMap().get("fldABC").isNull());
    assertTrue(fields.get("fldABC").isNull());
  }

  @Test
  void typedGettersHandleBothIntAndDoubleStorage() {
    Fields fields = new Fields(Map.of("int", LongNode.valueOf(7), "dbl", DoubleNode.valueOf(7.9)));
    assertEquals(7L, fields.getLong("int"));
    assertEquals(7L, fields.getLong("dbl"));
    assertEquals(7.0, fields.getDouble("int"));
    assertEquals(7.9, fields.getDouble("dbl"));
    assertNull(fields.getLong("missing"));
  }

  @Test
  void typedStringGetterRejectsNonStrings() {
    Fields fields = new Fields(Map.of("n", LongNode.valueOf(1), "s", TextNode.valueOf("x")));
    assertNull(fields.getString("n"));
    assertEquals("x", fields.getString("s"));
  }

  @Test
  void setStringsEncodesAStringArray() {
    Fields fields = new Fields();
    fields.setStrings("fldTags", List.of("a", "b"));
    assertEquals(
        List.of("a", "b"), fields.getArray("fldTags").stream().map(JsonNode::asText).toList());
  }

  @Test
  void serializationRoundTripPreservesStorageButDropsNameToId() throws Exception {
    Fields original = makeFields();
    String encoded = AirtableJson.MAPPER.writeValueAsString(original);
    Fields decoded = AirtableJson.MAPPER.readValue(encoded, Fields.class);
    assertEquals(original.toMap(), decoded.toMap());
    assertEquals(Map.of(), decoded.getNameToId());
  }

  private static final class RecordEnvelope {
    @JsonProperty("id")
    private String id;

    @JsonProperty("fields")
    private Fields fields = new Fields();

    public RecordEnvelope() {}
  }

  @Test
  void missingFieldsObjectDecodesWithoutThrowing() throws Exception {
    // Sparse Airtable responses can omit `fields` entirely.
    RecordEnvelope record =
        AirtableJson.MAPPER.readValue("{\"id\": \"recX\"}", RecordEnvelope.class);
    assertEquals(0, record.fields.count());
  }
}
