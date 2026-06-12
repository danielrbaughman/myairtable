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

  /** A list of values; entries can be {@code null} (Airtable emits sparse lookup arrays). */
  record Multiple<T>(List<T> values) implements VecOrValue<T> {}

  /**
   * All values as a list: a {@link Single} yields a one-element list, a {@link Multiple} yields its
   * entries (including {@code null}s). DX helper mirroring Kotlin's {@code VecOrValue<T>.values}.
   */
  default List<T> values() {
    return switch (this) {
      case Single<T> s -> s.value() == null ? List.of() : java.util.Collections.singletonList(s.value());
      case Multiple<T> m -> m.values() == null ? List.of() : m.values();
    };
  }
}
