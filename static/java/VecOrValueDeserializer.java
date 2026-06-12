// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.BeanProperty;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.deser.ContextualDeserializer;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * Structural-peek deserializer for {@link VecOrValue}: a JSON array decodes as {@link
 * VecOrValue.Multiple} (element-by-element so {@code null} entries survive), anything else as
 * {@link VecOrValue.Single}.
 *
 * <p>Element type capture mirrors {@link MaybeSpecialOrErrorDeserializer}; when the element type
 * is itself {@code MaybeSpecialOrError<...>}, per-element decoding flows through {@code
 * readTreeAsValue}, which contextualizes the inner deserializer (the nested {@code
 * VecOrValue<MaybeSpecialOrError<T>>} path).
 */
public final class VecOrValueDeserializer extends JsonDeserializer<VecOrValue<?>>
    implements ContextualDeserializer {

  private final JavaType elementType;

  public VecOrValueDeserializer() {
    this.elementType = null;
  }

  private VecOrValueDeserializer(JavaType elementType) {
    this.elementType = elementType;
  }

  @Override
  public JsonDeserializer<?> createContextual(DeserializationContext ctxt, BeanProperty property)
      throws JsonMappingException {
    JavaType wrapperType = property != null ? property.getType() : ctxt.getContextualType();
    JavaType contained =
        wrapperType != null && wrapperType.containedTypeCount() > 0
            ? wrapperType.containedType(0)
            : null;
    return new VecOrValueDeserializer(contained);
  }

  @Override
  public VecOrValue<?> deserialize(JsonParser p, DeserializationContext ctxt) throws IOException {
    JsonNode node = ctxt.readTree(p);
    JavaType element = elementType != null ? elementType : ctxt.constructType(Object.class);
    if (node.isArray()) {
      List<Object> values = new ArrayList<>(node.size());
      for (JsonNode item : node) {
        values.add(item.isNull() ? null : ctxt.readTreeAsValue(item, element));
      }
      return new VecOrValue.Multiple<>(values);
    }
    return new VecOrValue.Single<>(ctxt.readTreeAsValue(node, element));
  }
}
