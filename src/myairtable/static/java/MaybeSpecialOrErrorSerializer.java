// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;

/**
 * Serializer for {@link MaybeSpecialOrError}: {@code Value} writes the bare value, {@code
 * Special}/{@code Error} write their wire object forms. Encode parity is required for {@code
 * toRecord()} round-trips.
 */
public final class MaybeSpecialOrErrorSerializer extends JsonSerializer<MaybeSpecialOrError<?>> {

  @Override
  public void serialize(
      MaybeSpecialOrError<?> value, JsonGenerator gen, SerializerProvider provider)
      throws IOException {
    switch (value) {
      case MaybeSpecialOrError.Value<?> v -> provider.defaultSerializeValue(v.value(), gen);
      case MaybeSpecialOrError.Special<?> s -> provider.defaultSerializeValue(s.special(), gen);
      case MaybeSpecialOrError.Error<?> e -> provider.defaultSerializeValue(e.error(), gen);
    }
  }
}
