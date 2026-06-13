package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin myairtable-yvb3 (TestDxHelpers.kt) — DX additions: {@code
 * AirtableModel.requireId()}, {@code MaybeSpecialOrError} value access, {@code
 * VecOrValue.cleanValues}, {@code AirtableQuery.withView}.
 *
 * <p>Adaptation notes vs the Kotlin twin: Kotlin's nullable-receiver extensions ({@code
 * MaybeSpecialOrError<T>?.value}, {@code VecOrValue<MaybeSpecialOrError<T>>?.cleanValues}) have no
 * direct Java equivalent. Here {@code value()} is an instance method (a null field reference stays
 * caller-checked, as generated call sites do), and the clean-unwrap is the static {@link
 * VecOrValue#cleanValues}, which accepts a {@code null} argument to mirror the nullable receiver.
 */
class TestDxHelpers {

  /** Minimal model stub — only the id plumbing matters for requireId(). */
  private static final class DxStubModel implements AirtableModel {
    private String id;
    private Instant createdTime;
    private AirtableClient attachedClient;

    @Override
    public String getTableId() {
      return "tblStub";
    }

    @Override
    public String getId() {
      return id;
    }

    @Override
    public void setId(String id) {
      this.id = id;
    }

    @Override
    public Instant getCreatedTime() {
      return createdTime;
    }

    @Override
    public void setCreatedTime(Instant createdTime) {
      this.createdTime = createdTime;
    }

    @Override
    public AirtableClient getAttachedClient() {
      return attachedClient;
    }

    @Override
    public void setAttachedClient(AirtableClient client) {
      this.attachedClient = client;
    }

    @Override
    public void takeSnapshot() {}

    @Override
    public Map<String, JsonNode> dirtyFields() {
      return Map.of();
    }

    @Override
    public Map<String, JsonNode> toRecord() {
      return Map.of();
    }

    @Override
    public Map<String, JsonNode> toCreateFields() {
      return Map.of();
    }
  }

  @Nested
  class TestRequireId {
    @Test
    void requireIdReturnsServerAssignedId() {
      DxStubModel model = new DxStubModel();
      model.setId("recABC123");
      assertEquals("recABC123", model.requireId());
    }

    @Test
    void requireIdThrowsUnsavedModelWhenIdIsNull() {
      AirtableException.Api exception =
          assertThrows(AirtableException.Api.class, () -> new DxStubModel().requireId());
      assertEquals("UNSAVED_MODEL", exception.code());
    }
  }

  @Nested
  class TestComputedFieldSugar {
    @Test
    void valueIsNullOnNullReceiver() {
      // Kotlin's `field.value` works on a null receiver; the Java analog is the caller-side
      // null check generated call sites use over the instance method.
      MaybeSpecialOrError<Double> field = null;
      assertNull(field == null ? null : field.value());
    }

    @Test
    void valueUnwrapsValueVariant() {
      MaybeSpecialOrError<Double> field = new MaybeSpecialOrError.Value<>(2.5);
      assertEquals(2.5, field.value());
    }

    @Test
    void valueIsNullForSpecialAndErrorVariants() {
      MaybeSpecialOrError<Double> special =
          new MaybeSpecialOrError.Special<>(new SpecialNumber("NaN"));
      MaybeSpecialOrError<Double> error =
          new MaybeSpecialOrError.Error<>(new ErrorValue("#ERROR!"));
      assertNull(special.value());
      assertNull(error.value());
    }

    @Test
    void cleanValuesIsEmptyOnNullReceiver() {
      assertTrue(VecOrValue.<Double>cleanValues(null).isEmpty());
    }

    @Test
    void cleanValuesUnwrapsSingleShape() {
      VecOrValue<MaybeSpecialOrError<Double>> field =
          new VecOrValue.Single<>(new MaybeSpecialOrError.Value<>(1.0));
      assertEquals(List.of(1.0), VecOrValue.cleanValues(field));
    }

    @Test
    void cleanValuesSingleSentinelCollapsesToEmpty() {
      VecOrValue<MaybeSpecialOrError<Double>> field =
          new VecOrValue.Single<>(new MaybeSpecialOrError.Error<>(new ErrorValue("#ERROR!")));
      assertTrue(VecOrValue.cleanValues(field).isEmpty());
    }

    @Test
    void cleanValuesDropsNullsSpecialsAndErrorsFromListShape() {
      VecOrValue<MaybeSpecialOrError<Double>> field =
          new VecOrValue.Multiple<>(
              Arrays.asList(
                  new MaybeSpecialOrError.Value<>(1.0),
                  null,
                  new MaybeSpecialOrError.Special<>(new SpecialNumber("NaN")),
                  new MaybeSpecialOrError.Value<>(2.0),
                  new MaybeSpecialOrError.Error<>(new ErrorValue("#ERROR!"))));
      assertEquals(List.of(1.0, 2.0), VecOrValue.cleanValues(field));
    }

    @Test
    void multipleValuesIsRawAndCleanValuesIsNullSafe() {
      // JR-M7: the Multiple record accessor returns the RAW list (nulls kept) —
      // a same-named filtered interface default is impossible (shadowed). The
      // null-safe path is cleanValues, which drops null/special/error entries.
      VecOrValue.Multiple<String> raw = new VecOrValue.Multiple<>(Arrays.asList("a", null, "b"));
      assertEquals(Arrays.asList("a", null, "b"), raw.values());

      VecOrValue<MaybeSpecialOrError<String>> field =
          new VecOrValue.Multiple<>(
              Arrays.asList(
                  new MaybeSpecialOrError.Value<>("a"),
                  null,
                  new MaybeSpecialOrError.Value<>("b")));
      for (String v : VecOrValue.cleanValues(field)) {
        assertNotNull(v);
      }
      assertEquals(List.of("a", "b"), VecOrValue.cleanValues(field));
    }
  }

  @Nested
  class TestQueryWithView {
    /** Stand-in for a generated {@code {Table}View} enum constant. */
    private static final AirtableView STUB_VIEW = () -> "viwSTUB12345";

    @Test
    void withViewEncodesTheViewId() {
      List<AirtableQuery.Param> params = new AirtableQuery().withView(STUB_VIEW).toParameters();
      assertTrue(params.contains(new AirtableQuery.Param("view", "viwSTUB12345")));
    }

    @Test
    void withViewOverridesAnExistingView() {
      AirtableQuery query = new AirtableQuery().withView("viwOLD").withView(STUB_VIEW);
      assertEquals("viwSTUB12345", query.getView());
    }
  }
}
