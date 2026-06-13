package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.type.TypeFactory;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.2 — Computed-field error / special-value decoding. Parity with Kotlin/Swift
 * TestSpecialErrorDecoding / Rust test_special_error_deser.
 *
 * <p>Airtable returns {@code {"specialValue": "NaN"}} / {@code {"error": "#ERROR!"}} objects for
 * formula / rollup / lookup fields whose computation is non-finite or fails. Object forms must
 * decode; array forms must NOT (regression: lookup arrays like ["Lab Name"] must never collapse
 * into Special/Error).
 */
class TestSpecialErrorDecoding {

  private static JavaType maybeOf(Class<?> element) {
    return AirtableJson.MAPPER
        .getTypeFactory()
        .constructParametricType(MaybeSpecialOrError.class, element);
  }

  private static JavaType vecOfMaybe(Class<?> element) {
    TypeFactory tf = AirtableJson.MAPPER.getTypeFactory();
    return tf.constructParametricType(
        VecOrValue.class, tf.constructParametricType(MaybeSpecialOrError.class, element));
  }

  @SuppressWarnings("unchecked")
  private static <T> MaybeSpecialOrError<T> decodeMaybe(String raw, Class<T> element)
      throws Exception {
    return (MaybeSpecialOrError<T>) AirtableJson.MAPPER.readValue(raw, maybeOf(element));
  }

  @SuppressWarnings("unchecked")
  private static <T> VecOrValue<MaybeSpecialOrError<T>> decodeVec(String raw, Class<T> element)
      throws Exception {
    return (VecOrValue<MaybeSpecialOrError<T>>)
        AirtableJson.MAPPER.readValue(raw, vecOfMaybe(element));
  }

  // ---- SpecialNumber / ErrorValue --------------------------------------------

  @Test
  void specialNumberAcceptsObjectForm() throws Exception {
    assertEquals(
        "NaN",
        AirtableJson.MAPPER
            .readValue("{\"specialValue\":\"NaN\"}", SpecialNumber.class)
            .specialValue());
    assertEquals(
        "Infinity",
        AirtableJson.MAPPER
            .readValue("{\"specialValue\":\"Infinity\"}", SpecialNumber.class)
            .specialValue());
  }

  @Test
  void specialNumberRejectsArrayForm() {
    assertThrows(
        Exception.class, () -> AirtableJson.MAPPER.readValue("[\"NaN\"]", SpecialNumber.class));
  }

  @Test
  void errorValueAcceptsObjectForm() throws Exception {
    assertEquals(
        "#ERROR!",
        AirtableJson.MAPPER.readValue("{\"error\":\"#ERROR!\"}", ErrorValue.class).error());
  }

  @Test
  void errorValueRejectsArrayForm() {
    assertThrows(
        Exception.class, () -> AirtableJson.MAPPER.readValue("[\"#ERROR!\"]", ErrorValue.class));
  }

  // ---- MaybeSpecialOrError ----------------------------------------------------

  @Test
  void maybeDecodesValue() throws Exception {
    assertEquals(new MaybeSpecialOrError.Value<>(42.5), decodeMaybe("42.5", Double.class));
  }

  @Test
  void maybeDecodesSpecial() throws Exception {
    assertEquals(
        new MaybeSpecialOrError.Special<Double>(new SpecialNumber("NaN")),
        decodeMaybe("{\"specialValue\":\"NaN\"}", Double.class));
  }

  @Test
  void maybeDecodesError() throws Exception {
    assertEquals(
        new MaybeSpecialOrError.Error<Double>(new ErrorValue("#ERROR!")),
        decodeMaybe("{\"error\":\"#ERROR!\"}", Double.class));
  }

  @Test
  void maybeStringParsesPlainString() throws Exception {
    assertEquals("Stukenholtz", decodeMaybe("\"Stukenholtz\"", String.class).value());
  }

  @Test
  void maybeStringRejectsLookupArray() {
    // Regression: ["Stukenholtz"] must not accidentally decode as Special or Value.
    assertThrows(Exception.class, () -> decodeMaybe("[\"Stukenholtz\"]", String.class));
  }

  @Test
  void maybeHelpers() {
    MaybeSpecialOrError<Integer> v = new MaybeSpecialOrError.Value<>(42);
    assertInstanceOf(MaybeSpecialOrError.Value.class, v);
    assertEquals(42, (int) v.value());

    MaybeSpecialOrError<Integer> e = new MaybeSpecialOrError.Error<>(new ErrorValue("#ERROR!"));
    assertInstanceOf(MaybeSpecialOrError.Error.class, e);
    assertNull(e.value());
    assertEquals("#ERROR!", ((MaybeSpecialOrError.Error<Integer>) e).error().error());

    MaybeSpecialOrError<Integer> s = new MaybeSpecialOrError.Special<>(new SpecialNumber("NaN"));
    assertInstanceOf(MaybeSpecialOrError.Special.class, s);
    assertNull(s.value());
    assertEquals("NaN", ((MaybeSpecialOrError.Special<Integer>) s).special().specialValue());
  }

  // ---- VecOrValue --------------------------------------------------------------

  @Test
  void vecOrValueSingle() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v = decodeVec("\"hello\"", String.class);
    assertEquals("hello", ((VecOrValue.Single<MaybeSpecialOrError<String>>) v).value().value());
  }

  @Test
  void vecOrValueMultiple() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v =
        decodeVec("[\"Stukenholtz Laboratory Inc\"]", String.class);
    assertEquals(1, ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v).values().size());
    assertEquals(
        List.of("Stukenholtz Laboratory Inc"),
        ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v)
            .values().stream()
                .filter(Objects::nonNull)
                .map(MaybeSpecialOrError::value)
                .filter(Objects::nonNull)
                .toList());
  }

  @Test
  void vecOrValueNullableItemsPreserved() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v = decodeVec("[\"a\", null, \"b\"]", String.class);
    List<MaybeSpecialOrError<String>> items =
        ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v).values();
    assertEquals(3, items.size());
    assertNull(items.get(1));
  }

  @Test
  void vecOrValueAllNulls() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v = decodeVec("[null, null]", String.class);
    List<MaybeSpecialOrError<String>> items =
        ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v).values();
    assertEquals(2, items.size());
    // Java's values() preserves null entries (unlike Kotlin's filterNotNull helper):
    // the flattened non-null view is empty.
    assertTrue(
        ((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v)
            .values().stream().filter(Objects::nonNull).toList().isEmpty());
  }

  @Test
  void vecOrValueEmpty() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v = decodeVec("[]", String.class);
    assertTrue(((VecOrValue.Multiple<MaybeSpecialOrError<String>>) v).values().isEmpty());
  }

  @Test
  void vecOrValueSpecialNumberObject() throws Exception {
    VecOrValue<MaybeSpecialOrError<Double>> v =
        decodeVec("{\"specialValue\":\"NaN\"}", Double.class);
    MaybeSpecialOrError<Double> single =
        ((VecOrValue.Single<MaybeSpecialOrError<Double>>) v).value();
    assertEquals("NaN", ((MaybeSpecialOrError.Special<Double>) single).special().specialValue());
  }

  @Test
  void vecOrValueErrorValueObject() throws Exception {
    VecOrValue<MaybeSpecialOrError<Double>> v = decodeVec("{\"error\":\"#ERROR!\"}", Double.class);
    MaybeSpecialOrError<Double> single =
        ((VecOrValue.Single<MaybeSpecialOrError<Double>>) v).value();
    assertEquals("#ERROR!", ((MaybeSpecialOrError.Error<Double>) single).error().error());
  }

  @Test
  void vecOrValueMixedArray() throws Exception {
    VecOrValue<MaybeSpecialOrError<Integer>> v =
        decodeVec("[1, {\"specialValue\":\"NaN\"}, {\"error\":\"#ERROR!\"}, null]", Integer.class);
    List<MaybeSpecialOrError<Integer>> items =
        ((VecOrValue.Multiple<MaybeSpecialOrError<Integer>>) v).values();
    assertEquals(4, items.size());
    assertEquals(1, (int) items.get(0).value());
    assertEquals(
        "NaN", ((MaybeSpecialOrError.Special<Integer>) items.get(1)).special().specialValue());
    assertEquals("#ERROR!", ((MaybeSpecialOrError.Error<Integer>) items.get(2)).error().error());
    assertNull(items.get(3));
  }

  // ---- Round-trips --------------------------------------------------------------

  @Test
  void specialNumberRoundTrip() throws Exception {
    SpecialNumber original = new SpecialNumber("NaN");
    String encoded = AirtableJson.MAPPER.writeValueAsString(original);
    assertEquals("{\"specialValue\":\"NaN\"}", encoded);
    assertEquals(original, AirtableJson.MAPPER.readValue(encoded, SpecialNumber.class));
  }

  @Test
  void maybeEncodesUntagged() throws Exception {
    MaybeSpecialOrError<Integer> v = new MaybeSpecialOrError.Value<>(7);
    assertEquals("7", AirtableJson.MAPPER.writeValueAsString(v));
    MaybeSpecialOrError<Integer> e = new MaybeSpecialOrError.Error<>(new ErrorValue("#ERROR!"));
    assertEquals("{\"error\":\"#ERROR!\"}", AirtableJson.MAPPER.writeValueAsString(e));
  }

  @Test
  void vecOrValueSerializesMultipleWithNulls() throws Exception {
    VecOrValue<MaybeSpecialOrError<String>> v =
        new VecOrValue.Multiple<>(Arrays.asList(new MaybeSpecialOrError.Value<>("a"), null));
    assertEquals("[\"a\",null]", AirtableJson.MAPPER.writeValueAsString(v));
  }

  // ---- Duration codec (wire = seconds) -------------------------------------------

  @Test
  void durationDecodesWireSeconds() throws Exception {
    Map<String, Double> box =
        AirtableJson.MAPPER.readValue(
            "{\"d\": 3600.0}", new TypeReference<Map<String, Double>>() {});
    assertEquals(3600.0, box.get("d"));
    assertEquals(Duration.ofSeconds(1), AirtableJson.MAPPER.readValue("1", Duration.class));
    assertEquals(Duration.ofSeconds(3600), AirtableJson.MAPPER.readValue("3600", Duration.class));
  }

  @Test
  void durationEncodesWireSeconds() throws Exception {
    // Kotlin emits "90.0"; the Java codec deliberately writes whole seconds as an
    // integer (locked by TestPojoModel.durationEncodesAsNumericSecondsNotIso).
    assertEquals("90", AirtableJson.MAPPER.writeValueAsString(Duration.ofSeconds(90)));
    assertEquals("1.5", AirtableJson.MAPPER.writeValueAsString(Duration.ofMillis(1500)));
  }
}

/**
 * myairtable-dmiw — sentinel objects with sibling keys still decode as Special/Error (containment
 * match, mirroring Swift's lenient Codable).
 */
class TestSentinelSiblingKeys {

  @SuppressWarnings("unchecked")
  private static MaybeSpecialOrError<Double> decode(String raw) throws Exception {
    return (MaybeSpecialOrError<Double>)
        AirtableJson.MAPPER.readValue(
            raw,
            AirtableJson.MAPPER
                .getTypeFactory()
                .constructParametricType(MaybeSpecialOrError.class, Double.class));
  }

  @Test
  void specialWithSiblingKeyStillDecodesAsSpecial() throws Exception {
    MaybeSpecialOrError<Double> v = decode("{\"specialValue\":\"NaN\",\"future\":1}");
    assertEquals("NaN", ((MaybeSpecialOrError.Special<Double>) v).special().specialValue());
  }

  @Test
  void errorWithSiblingKeyStillDecodesAsError() throws Exception {
    MaybeSpecialOrError<Double> v = decode("{\"error\":\"#ERROR!\",\"detail\":\"x\"}");
    assertEquals("#ERROR!", ((MaybeSpecialOrError.Error<Double>) v).error().error());
  }
}
