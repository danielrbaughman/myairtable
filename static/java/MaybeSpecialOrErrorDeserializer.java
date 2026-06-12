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

/**
 * Structural-peek deserializer for {@link MaybeSpecialOrError}.
 *
 * <p>Reads the subtree as a {@link JsonNode} and dispatches: an object carrying a {@code
 * "specialValue"} key decodes as {@link MaybeSpecialOrError.Special}; an object carrying an {@code
 * "error"} key decodes as {@link MaybeSpecialOrError.Error}; anything else decodes as the element
 * type {@code T} into {@link MaybeSpecialOrError.Value}. This is the Jackson analog of the Kotlin
 * {@code decodeJsonElement()} peek pattern.
 *
 * <p>The element type is captured via {@link ContextualDeserializer}: Jackson calls {@link
 * #createContextual} with the declared field type (which carries the concrete generic argument),
 * or with the contextual type when resolved from inside another deserializer (the nested {@code
 * VecOrValue<MaybeSpecialOrError<T>>} path).
 */
public final class MaybeSpecialOrErrorDeserializer extends JsonDeserializer<MaybeSpecialOrError<?>>
    implements ContextualDeserializer {

  private final JavaType elementType;

  public MaybeSpecialOrErrorDeserializer() {
    this.elementType = null;
  }

  private MaybeSpecialOrErrorDeserializer(JavaType elementType) {
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
    return new MaybeSpecialOrErrorDeserializer(contained);
  }

  @Override
  public MaybeSpecialOrError<?> deserialize(JsonParser p, DeserializationContext ctxt)
      throws IOException {
    JsonNode node = ctxt.readTree(p);
    if (node.isObject() && node.has("specialValue")) {
      return new MaybeSpecialOrError.Special<>(
          ctxt.readTreeAsValue(node, ctxt.constructType(SpecialNumber.class)));
    }
    if (node.isObject() && node.has("error")) {
      return new MaybeSpecialOrError.Error<>(
          ctxt.readTreeAsValue(node, ctxt.constructType(ErrorValue.class)));
    }
    Object value =
        elementType != null
            ? ctxt.readTreeAsValue(node, elementType)
            : ctxt.readTreeAsValue(node, ctxt.constructType(Object.class));
    return new MaybeSpecialOrError.Value<>(value);
  }
}
