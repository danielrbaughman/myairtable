package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * F1.13 PHASE 0 GATE (java-plan-v2 §5 F1.13) — proves every risky Jackson foundation before any
 * generator templating:
 *
 * <p>(a) public no-arg ctor + field-access decode of @JsonProperty field-ID keys, including
 * computed (no-setter) fields; (b) field-level @JsonDeserialize ContextualDeserializer round-trips,
 * including the nested VecOrValue&lt;MaybeSpecialOrError&lt;String&gt;&gt; case, decode AND encode;
 * (c) Duration encodes as numeric seconds, never ISO "PT30S"; (d) @JsonIgnore snapshot +
 * writable-only payload builders; (e) package-vs-directory compile proof.
 */
class TestPojoModel {

  /**
   * Prototype of a generated model: writable fields get setters, computed fields are getter-only
   * (decode populates the private field directly). Field-ID keys via @JsonProperty; wrapper-typed
   * fields carry field-level @JsonDeserialize (java-plan-v2 §2.3.4).
   */
  static final class ProtoModel {
    @JsonProperty("fldPK")
    private String primaryKey;

    @JsonProperty("fldNum")
    private Double number;

    @JsonProperty("fldDate")
    private Instant date;

    @JsonProperty("fldDur")
    private Duration duration;

    @JsonProperty("fldAuto")
    @JsonDeserialize(using = MaybeSpecialOrErrorDeserializer.class)
    private MaybeSpecialOrError<Long> autoNumber;

    @JsonProperty("fldLookup")
    @JsonDeserialize(using = VecOrValueDeserializer.class)
    private VecOrValue<MaybeSpecialOrError<String>> lookup;

    @JsonIgnore private Map<String, JsonNode> snapshot = new HashMap<>();

    public ProtoModel() {}

    public String getPrimaryKey() {
      return primaryKey;
    }

    public void setPrimaryKey(String v) {
      primaryKey = v;
    }

    public Double getNumber() {
      return number;
    }

    public void setNumber(Double v) {
      number = v;
    }

    public Instant getDate() {
      return date;
    }

    public void setDate(Instant v) {
      date = v;
    }

    public Duration getDuration() {
      return duration;
    }

    public void setDuration(Duration v) {
      duration = v;
    }

    // Computed: getters only — no setter exists, decode-only by construction.
    public MaybeSpecialOrError<Long> getAutoNumber() {
      return autoNumber;
    }

    public VecOrValue<MaybeSpecialOrError<String>> getLookup() {
      return lookup;
    }

    /** Writable, non-null fields only — the create-payload contract. */
    public Map<String, JsonNode> toCreateFields() {
      Map<String, JsonNode> fields = new LinkedHashMap<>();
      putIfNotNull(fields, "fldPK", primaryKey);
      putIfNotNull(fields, "fldNum", number);
      putIfNotNull(fields, "fldDate", date);
      putIfNotNull(fields, "fldDur", duration);
      return fields;
    }

    public void takeSnapshot() {
      snapshot = new HashMap<>(allWritable());
    }

    /** Writable fields whose current value differs from the snapshot. */
    public Map<String, JsonNode> dirtyFields() {
      Map<String, JsonNode> dirty = new LinkedHashMap<>();
      for (Map.Entry<String, JsonNode> entry : allWritable().entrySet()) {
        JsonNode before = snapshot.getOrDefault(entry.getKey(), NullNode.getInstance());
        if (!before.equals(entry.getValue())) {
          dirty.put(entry.getKey(), entry.getValue());
        }
      }
      return dirty;
    }

    private Map<String, JsonNode> allWritable() {
      Map<String, JsonNode> fields = new LinkedHashMap<>();
      fields.put("fldPK", AirtableJson.MAPPER.valueToTree(primaryKey));
      fields.put("fldNum", AirtableJson.MAPPER.valueToTree(number));
      fields.put("fldDate", AirtableJson.MAPPER.valueToTree(date));
      fields.put("fldDur", AirtableJson.MAPPER.valueToTree(duration));
      return fields;
    }

    private static void putIfNotNull(Map<String, JsonNode> fields, String id, Object value) {
      if (value != null) {
        fields.put(id, AirtableJson.MAPPER.valueToTree(value));
      }
    }
  }

  // ---- (a) no-arg ctor + field-access decode --------------------------------

  @Test
  void decodePopulatesWritableAndComputedFields() throws Exception {
    String json =
        """
        {
          "fldPK": "rec-key",
          "fldNum": 42.0,
          "fldDate": "2024-01-15T10:30:00.000Z",
          "fldDur": 90,
          "fldAuto": 7,
          "fldLookup": ["a", "b"],
          "fldUnknownFutureField": {"nested": true}
        }
        """;
    ProtoModel model = AirtableJson.MAPPER.readValue(json, ProtoModel.class);
    assertEquals("rec-key", model.getPrimaryKey());
    assertEquals(42.0, model.getNumber());
    assertEquals(Instant.parse("2024-01-15T10:30:00Z"), model.getDate());
    assertEquals(Duration.ofSeconds(90), model.getDuration());
    assertEquals(7L, model.getAutoNumber().value());
    assertEquals(
        2, ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) model.getLookup()).values().size());
  }

  @Test
  void decodeOfSparseJsonLeavesFieldsNull() throws Exception {
    ProtoModel model = AirtableJson.MAPPER.readValue("{}", ProtoModel.class);
    assertNull(model.getPrimaryKey());
    assertNull(model.getAutoNumber());
    assertNull(model.getLookup());
  }

  // ---- (b) contextual deserializer round-trips ------------------------------

  @Test
  void computedLongDecodesAsTypedValue() throws Exception {
    ProtoModel model = AirtableJson.MAPPER.readValue("{\"fldAuto\": 42}", ProtoModel.class);
    assertInstanceOf(MaybeSpecialOrError.Value.class, model.getAutoNumber());
    assertEquals(42L, model.getAutoNumber().value());
  }

  @Test
  void computedSpecialValueDecodes() throws Exception {
    ProtoModel model =
        AirtableJson.MAPPER.readValue(
            "{\"fldAuto\": {\"specialValue\": \"NaN\"}}", ProtoModel.class);
    assertInstanceOf(MaybeSpecialOrError.Special.class, model.getAutoNumber());
    assertEquals(
        "NaN",
        ((MaybeSpecialOrError.Special<Long>) model.getAutoNumber()).special().specialValue());
    assertNull(model.getAutoNumber().value());
  }

  @Test
  void computedErrorDecodes() throws Exception {
    ProtoModel model =
        AirtableJson.MAPPER.readValue("{\"fldAuto\": {\"error\": \"#ERROR!\"}}", ProtoModel.class);
    assertInstanceOf(MaybeSpecialOrError.Error.class, model.getAutoNumber());
    assertEquals(
        "#ERROR!", ((MaybeSpecialOrError.Error<Long>) model.getAutoNumber()).error().error());
  }

  @Test
  void nestedVecOrValueOfMaybeSpecialDecodesArrayForm() throws Exception {
    String json =
        """
        {"fldLookup": ["a", null, {"specialValue": "Infinity"}, {"error": "#ERROR!"}]}
        """;
    ProtoModel model = AirtableJson.MAPPER.readValue(json, ProtoModel.class);
    assertInstanceOf(VecOrValue.Multiple.class, model.getLookup());
    var values = ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) model.getLookup()).values();
    assertEquals(4, values.size());
    assertEquals("a", values.get(0).value());
    assertNull(values.get(1));
    assertInstanceOf(MaybeSpecialOrError.Special.class, values.get(2));
    assertInstanceOf(MaybeSpecialOrError.Error.class, values.get(3));
  }

  @Test
  void nestedVecOrValueOfMaybeSpecialDecodesScalarForm() throws Exception {
    ProtoModel model = AirtableJson.MAPPER.readValue("{\"fldLookup\": \"solo\"}", ProtoModel.class);
    assertInstanceOf(VecOrValue.Single.class, model.getLookup());
    assertEquals(
        "solo",
        ((VecOrValue.Single<MaybeSpecialOrError<String>>) model.getLookup()).value().value());
  }

  @Test
  void wrapperTypesEncodeBackToWireShape() throws Exception {
    String json =
        """
        {"fldAuto": {"specialValue": "NaN"}, "fldLookup": ["a", null, {"error": "#ERROR!"}]}
        """;
    ProtoModel model = AirtableJson.MAPPER.readValue(json, ProtoModel.class);

    JsonNode autoNode = AirtableJson.MAPPER.valueToTree(model.getAutoNumber());
    assertTrue(autoNode.isObject());
    assertEquals("NaN", autoNode.get("specialValue").asText());

    JsonNode lookupNode = AirtableJson.MAPPER.valueToTree(model.getLookup());
    assertTrue(lookupNode.isArray());
    assertEquals("a", lookupNode.get(0).asText());
    assertTrue(lookupNode.get(1).isNull());
    assertEquals("#ERROR!", lookupNode.get(2).get("error").asText());
  }

  @Test
  void specialNumberAndErrorValueRecordsRoundTrip() throws Exception {
    SpecialNumber special =
        AirtableJson.MAPPER.readValue("{\"specialValue\": \"NaN\"}", SpecialNumber.class);
    assertEquals("NaN", special.specialValue());
    assertEquals(
        "NaN", AirtableJson.MAPPER.<JsonNode>valueToTree(special).get("specialValue").asText());

    ErrorValue error = AirtableJson.MAPPER.readValue("{\"error\": \"#ERROR!\"}", ErrorValue.class);
    assertEquals("#ERROR!", error.error());
    assertEquals("#ERROR!", AirtableJson.MAPPER.<JsonNode>valueToTree(error).get("error").asText());
  }

  // ---- (c) Duration & Instant wire formats ----------------------------------

  @Test
  void durationEncodesAsNumericSecondsNotIso() {
    JsonNode whole = AirtableJson.MAPPER.valueToTree(Duration.ofSeconds(30));
    assertTrue(whole.isNumber(), "Duration must encode as a number, got: " + whole);
    assertEquals(30, whole.asLong());

    JsonNode fractional = AirtableJson.MAPPER.valueToTree(Duration.ofMillis(1500));
    assertTrue(fractional.isNumber());
    assertEquals(1.5, fractional.asDouble());
  }

  @Test
  void durationDecodesFromNumericSeconds() throws Exception {
    assertEquals(Duration.ofSeconds(90), AirtableJson.MAPPER.readValue("90", Duration.class));
    assertEquals(Duration.ofMillis(1500), AirtableJson.MAPPER.readValue("1.5", Duration.class));
  }

  @Test
  void instantDecodesAllThreeAirtableFormats() throws Exception {
    assertEquals(
        Instant.parse("2024-01-15T10:30:00Z"),
        AirtableJson.MAPPER.readValue("\"2024-01-15T10:30:00.000Z\"", Instant.class));
    assertEquals(
        Instant.parse("2024-01-15T08:30:00Z"),
        AirtableJson.MAPPER.readValue("\"2024-01-15T10:30:00+02:00\"", Instant.class));
    assertEquals(
        Instant.parse("2024-01-15T00:00:00Z"),
        AirtableJson.MAPPER.readValue("\"2024-01-15\"", Instant.class));
  }

  @Test
  void instantEncodesAsIsoUtc() {
    JsonNode node = AirtableJson.MAPPER.valueToTree(Instant.parse("2024-01-15T10:30:00Z"));
    assertEquals("2024-01-15T10:30:00Z", node.asText());
  }

  // ---- (d) snapshot + writable-only payload builders -------------------------

  @Test
  void toCreateFieldsContainsOnlyNonNullWritableFields() throws Exception {
    String json = "{\"fldPK\": \"key\", \"fldAuto\": 7, \"fldLookup\": [\"x\"]}";
    ProtoModel model = AirtableJson.MAPPER.readValue(json, ProtoModel.class);
    Map<String, JsonNode> fields = model.toCreateFields();
    assertEquals(1, fields.size(), "computed + null writable fields must be excluded");
    assertEquals("key", fields.get("fldPK").asText());
  }

  @Test
  void dirtyFieldsReflectsOnlyChangesSinceSnapshot() throws Exception {
    ProtoModel model =
        AirtableJson.MAPPER.readValue("{\"fldPK\": \"key\", \"fldNum\": 1.0}", ProtoModel.class);
    model.takeSnapshot();
    assertTrue(model.dirtyFields().isEmpty());

    model.setNumber(2.0);
    model.setDuration(Duration.ofSeconds(30));
    Map<String, JsonNode> dirty = model.dirtyFields();
    assertEquals(2, dirty.size());
    assertEquals(2.0, dirty.get("fldNum").asDouble());
    assertEquals(30, dirty.get("fldDur").asLong());

    model.takeSnapshot();
    assertTrue(model.dirtyFields().isEmpty());
  }

  @Test
  void createPayloadSerializesTypedFieldsThroughSharedMapper() {
    ProtoModel model = new ProtoModel();
    model.setPrimaryKey("k");
    model.setDate(Instant.parse("2024-01-15T00:00:00Z"));
    model.setDuration(Duration.ofSeconds(45));
    Map<String, JsonNode> fields = model.toCreateFields();
    assertEquals("2024-01-15T00:00:00Z", fields.get("fldDate").asText());
    assertEquals(45, fields.get("fldDur").asLong());
    ObjectNode payload = AirtableJson.MAPPER.createObjectNode();
    fields.forEach(payload::set);
    assertEquals(3, payload.size());
  }

  // ---- (e) package-vs-directory compile proof --------------------------------

  @Test
  void packageDirMismatchedSourceCompilesAndLinks() {
    assertEquals("package-dir-mismatch-compiles", PackageDirMismatchProof.PROOF);
    assertEquals("0.0.1-dev", MyAirtableRuntimeInfo.VERSION);
  }
}
