// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import java.util.List;

/**
 * A field value whose cardinality Airtable does not guarantee: either a single {@code T} or a list
 * of {@code T}. Used for lookup/rollup computed fields. Mirrors the Rust/Swift/Kotlin {@code
 * VecOrValue<T>} by name and shape.
 *
 * <p>Class-level {@code @JsonDeserialize} covers nested resolution; generated model fields also
 * carry a field-level annotation (java-plan-v2 §2.3.4).
 */
@JsonDeserialize(using = VecOrValueDeserializer.class)
@JsonSerialize(using = VecOrValueSerializer.class)
public sealed interface VecOrValue<T> permits VecOrValue.Single, VecOrValue.Multiple {

  /** A single scalar value. */
  record Single<T>(T value) implements VecOrValue<T> {}

  /**
   * A list of values whose entries can be {@code null} — Airtable emits sparse lookup arrays. The
   * {@code values()} record accessor returns the RAW list (nulls preserved); for the null- and
   * sentinel-free path use {@link VecOrValue#cleanValues}.
   *
   * <p>(There is intentionally no uniform filtered {@code values()} on the interface: a record
   * component named {@code values} already owns that method, so a same-named interface default
   * would be shadowed on {@code Multiple} — JR-M7. Access raw entries by pattern-matching the two
   * shapes, or use {@code cleanValues} for the common typed-unwrap.)
   */
  record Multiple<T>(List<T> values) implements VecOrValue<T> {}

  /**
   * All clean values — non-null, non-special, non-error — regardless of the single/list shape. A
   * {@code null} receiver yields an empty list; {@code null} entries and special/error sentinels
   * are dropped, so the result is always safe to iterate.
   *
   * <p>DX helper mirroring Kotlin's {@code VecOrValue<MaybeSpecialOrError<T>>?.cleanValues} for
   * generated lookup/rollup computed fields: {@code VecOrValue.cleanValues(model.getScores())}
   * instead of manual null-checks plus sentinel filtering. Static (not a default method) because
   * Java has no nullable-receiver extensions and the unwrapping is only defined when the element
   * type is {@link MaybeSpecialOrError}.
   */
  static <T> List<T> cleanValues(VecOrValue<MaybeSpecialOrError<T>> field) {
    if (field == null) {
      return List.of();
    }
    List<MaybeSpecialOrError<T>> raw =
        switch (field) {
          case Single<MaybeSpecialOrError<T>> s ->
              s.value() == null ? List.of() : java.util.Collections.singletonList(s.value());
          case Multiple<MaybeSpecialOrError<T>> m -> m.values() == null ? List.of() : m.values();
        };
    List<T> clean = new java.util.ArrayList<>();
    for (MaybeSpecialOrError<T> entry : raw) {
      if (entry != null && entry.value() != null) {
        clean.add(entry.value());
      }
    }
    return List.copyOf(clean);
  }
}
