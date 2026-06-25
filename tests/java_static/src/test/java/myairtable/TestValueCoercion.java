package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.BooleanNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.8 — V/N/S/A/AN/AS/D/isTruthy coercion helpers over JsonNode. Parity: coercion
 * section of Kotlin TestValueCoercion / Swift TestAirtableRuntime.
 */
class TestValueCoercion {

  private static ArrayNode array(JsonNode... items) {
    ArrayNode node = AirtableJson.MAPPER.createArrayNode();
    for (JsonNode item : items) {
      node.add(item);
    }
    return node;
  }

  // ---- N -----------------------------------------------------------------------

  @Test
  void nCoercesNumbersBoolsStrings() {
    assertEquals(0.0, AirtableRuntime.N(null));
    assertEquals(0.0, AirtableRuntime.N(NullNode.getInstance()));
    assertEquals(1.0, AirtableRuntime.N(BooleanNode.TRUE));
    assertEquals(0.0, AirtableRuntime.N(BooleanNode.FALSE));
    assertEquals(42.0, AirtableRuntime.N(LongNode.valueOf(42)));
    assertEquals(2.5, AirtableRuntime.N(DoubleNode.valueOf(2.5)));
    assertEquals(7.0, AirtableRuntime.N(TextNode.valueOf(" 7 ")));
    assertEquals(0.0, AirtableRuntime.N(TextNode.valueOf("abc")));
    assertEquals(0.0, AirtableRuntime.N(AirtableJson.MAPPER.createObjectNode()));
  }

  @Test
  void nTakesFirstElementOfArray() {
    assertEquals(3.0, AirtableRuntime.N(array(LongNode.valueOf(3), LongNode.valueOf(9))));
    assertEquals(0.0, AirtableRuntime.N(array()));
  }

  // ---- S -----------------------------------------------------------------------

  @Test
  void sCoercesAllShapes() {
    assertEquals("", AirtableRuntime.S(null));
    assertEquals("", AirtableRuntime.S(NullNode.getInstance()));
    assertEquals("1", AirtableRuntime.S(BooleanNode.TRUE));
    assertEquals("0", AirtableRuntime.S(BooleanNode.FALSE));
    assertEquals("42", AirtableRuntime.S(LongNode.valueOf(42)));
    assertEquals("hello", AirtableRuntime.S(TextNode.valueOf("hello")));
    assertEquals("", AirtableRuntime.S(AirtableJson.MAPPER.createObjectNode()));
  }

  @Test
  void sStripsTrailingZeroFromWholeFloats() {
    assertEquals("3", AirtableRuntime.S(DoubleNode.valueOf(3.0)));
    assertEquals("2.5", AirtableRuntime.S(DoubleNode.valueOf(2.5)));
  }

  @Test
  void sJoinsArrayWithCommaSpace() {
    assertEquals("a, b", AirtableRuntime.S(array(TextNode.valueOf("a"), TextNode.valueOf("b"))));
    assertEquals("", AirtableRuntime.S(array()));
  }

  // ---- A / AN / AS ---------------------------------------------------------------

  @Test
  void aFlattensOneLevelAndDropsJavaNulls() {
    List<JsonNode> flat =
        AirtableRuntime.A(
            Arrays.asList(
                LongNode.valueOf(1), null, array(LongNode.valueOf(2), LongNode.valueOf(3))));
    assertEquals(List.of(1.0, 2.0, 3.0), flat.stream().map(AirtableRuntime::N).toList());
  }

  @Test
  void anAndAsCoerce() {
    List<JsonNode> args = List.of(TextNode.valueOf("2"), array(LongNode.valueOf(3)));
    assertEquals(List.of(2.0, 3.0), AirtableRuntime.AN(args));
    assertEquals(List.of("2", "3"), AirtableRuntime.AS(args));
  }

  // ---- V -----------------------------------------------------------------------

  @Test
  void vWrapsPrimitivesAndLists() {
    assertEquals(NullNode.getInstance(), AirtableRuntime.V(null));
    assertEquals(TextNode.valueOf("x"), AirtableRuntime.V("x"));
    assertEquals(LongNode.valueOf(42L), AirtableRuntime.V(42L));
    assertEquals(DoubleNode.valueOf(2.5), AirtableRuntime.V(2.5));
    assertEquals(BooleanNode.TRUE, AirtableRuntime.V(true));
    JsonNode list = AirtableRuntime.V(List.of("a", "b"));
    assertTrue(list.isArray());
    assertEquals(List.of("a", "b"), List.of(list.get(0).asText(), list.get(1).asText()));
  }

  @Test
  void vPassesThroughJsonElements() {
    ArrayNode element = array(LongNode.valueOf(1));
    assertEquals(element, AirtableRuntime.V(element));
    assertEquals(NullNode.getInstance(), AirtableRuntime.V((JsonNode) null));
  }

  @Test
  void vEncodesInstantAsIso8601String() {
    Instant instant = Instant.ofEpochSecond(1_705_314_600L);
    assertEquals(TextNode.valueOf("2024-01-15T10:30:00Z"), AirtableRuntime.V(instant));
  }

  @Test
  void vEncodesDurationAsWireSeconds() {
    assertEquals(DoubleNode.valueOf(90.0), AirtableRuntime.V(Duration.ofSeconds(90)));
  }

  // ---- D -----------------------------------------------------------------------

  @Test
  void dParsesIsoStringsAndTimestamps() {
    assertEquals(
        1_705_314_600L,
        AirtableRuntime.D(TextNode.valueOf("2024-01-15T10:30:00.000Z")).getEpochSecond());
    assertEquals(
        1_705_276_800L, AirtableRuntime.D(TextNode.valueOf("2024-01-15")).getEpochSecond());
    assertEquals(
        1_705_314_600L, AirtableRuntime.D(LongNode.valueOf(1_705_314_600L)).getEpochSecond());
    assertNull(AirtableRuntime.D(TextNode.valueOf("garbage")));
    assertNull(AirtableRuntime.D(null));
    assertNull(AirtableRuntime.D(NullNode.getInstance()));
  }

  // ---- isTruthy -------------------------------------------------------------------

  @Test
  void truthinessMatchesAirtableSemantics() {
    assertFalse(AirtableRuntime.isTruthy(null));
    assertFalse(AirtableRuntime.isTruthy(NullNode.getInstance()));
    assertFalse(AirtableRuntime.isTruthy(LongNode.valueOf(0)));
    assertFalse(AirtableRuntime.isTruthy(DoubleNode.valueOf(0.0)));
    assertFalse(AirtableRuntime.isTruthy(DoubleNode.valueOf(Double.NaN)));
    assertFalse(AirtableRuntime.isTruthy(TextNode.valueOf("")));
    assertFalse(AirtableRuntime.isTruthy(AirtableJson.MAPPER.createArrayNode()));
    assertFalse(AirtableRuntime.isTruthy(AirtableJson.MAPPER.createObjectNode()));
    assertFalse(AirtableRuntime.isTruthy(BooleanNode.FALSE));

    assertTrue(AirtableRuntime.isTruthy(BooleanNode.TRUE));
    assertTrue(AirtableRuntime.isTruthy(LongNode.valueOf(1)));
    assertTrue(AirtableRuntime.isTruthy(DoubleNode.valueOf(-0.5)));
    assertTrue(AirtableRuntime.isTruthy(TextNode.valueOf("x")));
    ArrayNode arrayWithNull = AirtableJson.MAPPER.createArrayNode();
    arrayWithNull.addNull();
    assertTrue(AirtableRuntime.isTruthy(arrayWithNull));
  }
}

/**
 * myairtable-4929 regression — the emitted equality shapes must EVALUATE correctly: raw node
 * equality made Double "5.0" != Long "5", so =/!= route through N()/S() coercion on both sides.
 */
class TestTranspiledEqualityShapes {

  @Test
  void numericEqualityShapeIsTrueForWholeNumberFields() {
    // {field} = 5 with field holding 5.0 — the pre-fix shape was constant-false.
    assertTrue(AirtableRuntime.N(AirtableRuntime.V(5.0)) == AirtableRuntime.N(LongNode.valueOf(5)));
    assertTrue(AirtableRuntime.N(AirtableRuntime.V(5)) == AirtableRuntime.N(LongNode.valueOf(5)));
    assertFalse(
        AirtableRuntime.N(AirtableRuntime.V(4.0)) == AirtableRuntime.N(LongNode.valueOf(5)));
  }

  @Test
  void numericInequalityShapeIsFalseForEqualValues() {
    assertFalse(
        AirtableRuntime.N(AirtableRuntime.V(5.0)) != AirtableRuntime.N(LongNode.valueOf(5)));
    assertTrue(AirtableRuntime.N(AirtableRuntime.V(4.0)) != AirtableRuntime.N(LongNode.valueOf(5)));
  }

  @Test
  void stringEqualityShapeCoercesBothSides() {
    assertTrue(
        AirtableRuntime.S(AirtableRuntime.V("hi"))
            .equals(AirtableRuntime.S(TextNode.valueOf("hi"))));
    assertTrue(
        AirtableRuntime.S(AirtableRuntime.V(5.0)).equals(AirtableRuntime.S(LongNode.valueOf(5))),
        "S() collapses 5.0 to '5'");
    assertFalse(
        AirtableRuntime.S(AirtableRuntime.V("hi"))
            .equals(AirtableRuntime.S(TextNode.valueOf("ho"))));
  }
}

/**
 * myairtable-w3rk regression — V() must resolve Instant nested inside generics via the shared
 * mapper instead of silently degrading to NullNode (which made toRecord() drop computed date fields
 * and formulas referencing them evaluate as BLANK).
 */
class TestVGenericSerializerResolution {

  private final Instant instant = Instant.ofEpochSecond(1_705_314_600L);

  @Test
  void vResolvesInstantInsideMaybeSpecialOrError() {
    MaybeSpecialOrError<Instant> wrapped = new MaybeSpecialOrError.Value<>(instant);
    assertEquals(TextNode.valueOf("2024-01-15T10:30:00Z"), AirtableRuntime.V(wrapped));
  }

  @Test
  void vResolvesInstantInsideVecOrValue() {
    VecOrValue<MaybeSpecialOrError<Instant>> wrapped =
        new VecOrValue.Single<>(new MaybeSpecialOrError.Value<>(instant));
    assertEquals(TextNode.valueOf("2024-01-15T10:30:00Z"), AirtableRuntime.V(wrapped));
  }

  @Test
  void vStillDegradesUnserializableTypesToNull() {
    // No detectable properties → Jackson's empty-bean failure → V() degrades to NullNode.
    final class NotSerializable {
      NotSerializable(int x) {}
    }
    assertEquals(NullNode.getInstance(), AirtableRuntime.V(new NotSerializable(1)));
  }
}
