// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import java.io.IOException;

/**
 * Serializer for {@link VecOrValue}: {@code Single} writes the bare value, {@code Multiple} writes
 * a JSON array (preserving {@code null} entries).
 */
public final class VecOrValueSerializer extends JsonSerializer<VecOrValue<?>> {

  @Override
  public void serialize(VecOrValue<?> value, JsonGenerator gen, SerializerProvider provider)
      throws IOException {
    switch (value) {
      case VecOrValue.Single<?> s -> provider.defaultSerializeValue(s.value(), gen);
      case VecOrValue.Multiple<?> m -> {
        gen.writeStartArray();
        for (Object item : m.values()) {
          if (item == null) {
            gen.writeNull();
          } else {
            provider.defaultSerializeValue(item, gen);
          }
        }
        gen.writeEndArray();
      }
    }
  }
}
