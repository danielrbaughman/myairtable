// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

/**
 * A computed-field value that may instead be an Airtable special value or error.
 *
 * <p>Airtable returns {@code {"specialValue": ...}} / {@code {"error": ...}} objects for computed
 * fields whose evaluation produced a non-finite number or an error, in place of the plain value.
 * Mirrors the Rust/Swift/Kotlin {@code MaybeSpecialOrError<T>} by name and shape.
 *
 * <p>The class-level {@code @JsonDeserialize} makes the type resolvable when it appears NESTED
 * (e.g. as the element of {@code VecOrValue<MaybeSpecialOrError<T>>}); generated model fields
 * ALSO carry a field-level {@code @JsonDeserialize} so top-level contextualization is never left
 * to interface-level resolution alone (java-plan-v2 §2.3.4).
 */
@JsonDeserialize(using = MaybeSpecialOrErrorDeserializer.class)
@JsonSerialize(using = MaybeSpecialOrErrorSerializer.class)
public sealed interface MaybeSpecialOrError<T>
    permits MaybeSpecialOrError.Value, MaybeSpecialOrError.Special, MaybeSpecialOrError.Error {

  /** A plain, successfully computed value. */
  record Value<T>(T value) implements MaybeSpecialOrError<T> {}

  /** A special (non-finite) number such as {@code NaN} or {@code Infinity}. */
  record Special<T>(SpecialNumber special) implements MaybeSpecialOrError<T> {
    @Override
    public T value() {
      return null;
    }
  }

  /** A computed-field error such as {@code #ERROR!}. */
  record Error<T>(ErrorValue error) implements MaybeSpecialOrError<T> {
    @Override
    public T value() {
      return null;
    }
  }

  /**
   * The plain value, or {@code null} when this is a {@link Special} or {@link Error}. DX helper
   * mirroring Kotlin's {@code MaybeSpecialOrError<T>?.value}.
   */
  T value();
}
