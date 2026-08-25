// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The single shared {@link ObjectMapper} for the whole runtime — generated models, the client, and
 * the formula runtime all use {@code AirtableJson.MAPPER}. Never construct ad-hoc mappers.
 *
 * <p>Configuration contract (java-plan-v2 §2.3.1/§2.3.7):
 *
 * <ul>
 *   <li>Unknown wire properties are ignored (Airtable adds fields without notice).
 *   <li>Field-access mode: properties are discovered from {@code private} fields annotated
 *       {@code @JsonProperty}; getters/setters/creators are invisible. Generated models therefore
 *       need a public no-arg constructor and nothing else for decoding.
 *   <li>{@code null} values are omitted on encode (Airtable treats absent and null differently).
 *   <li>Only {@link AirtableJacksonModule} is registered — never {@code findAndRegisterModules()},
 *       which could pull in {@code jackson-datatype-jsr310} and shadow the numeric-seconds Duration
 *       codec.
 * </ul>
 */
public final class AirtableJson {

  public static final ObjectMapper MAPPER = create();

  private AirtableJson() {}

  private static ObjectMapper create() {
    ObjectMapper mapper = new ObjectMapper();
    mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
    mapper.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.NONE);
    mapper.setVisibility(PropertyAccessor.FIELD, JsonAutoDetect.Visibility.ANY);
    mapper.registerModule(new AirtableJacksonModule());
    return mapper;
  }

  /**
   * Reduce attachment cells to the only shape Airtable accepts when inserting.
   *
   * <p>Airtable returns attachments carrying read-only metadata ({@code id}, {@code size}, {@code
   * type}, {@code width}, {@code height}, {@code thumbnails}). On <b>create</b> it accepts only
   * {@code {"url": ...}} (optionally with {@code "filename"}) — sending an {@code id}, alone or
   * echoed alongside {@code url}, fails with {@code INVALID_ATTACHMENT_OBJECT}. Airtable re-ingests
   * the file and mints a fresh attachment id, which is what makes a duplicated record's attachment
   * independent of its source rather than an alias.
   *
   * <p>Create-only: on <b>update</b> an {@code id} is legal and means "retain this attachment".
   *
   * <p>Cells are recognised by shape rather than by field id, so this needs no generated metadata:
   * no other Airtable cell type is an array of objects carrying a {@code url} alongside an {@code
   * att}-prefixed id. Returns a new map; the caller's fields are never mutated.
   */
  public static Map<String, JsonNode> projectAttachmentsForCreate(Map<String, JsonNode> fields) {
    Map<String, JsonNode> projectedFields = new LinkedHashMap<>(fields);
    for (Map.Entry<String, JsonNode> entry : fields.entrySet()) {
      JsonNode value = entry.getValue();
      if (value == null || !value.isArray() || value.isEmpty()) {
        continue;
      }
      ArrayNode projected = MAPPER.createArrayNode();
      boolean isAttachmentCell = true;
      for (JsonNode item : value) {
        JsonNode url = item.get("url");
        JsonNode id = item.get("id");
        if (!item.isObject()
            || url == null
            || id == null
            || !id.isTextual()
            || !id.asText().startsWith("att")) {
          isAttachmentCell = false;
          break;
        }
        ObjectNode projectedItem = MAPPER.createObjectNode();
        projectedItem.set("url", url.deepCopy());
        JsonNode filename = item.get("filename");
        if (filename != null && !filename.isNull()) {
          projectedItem.set("filename", filename.deepCopy());
        }
        projected.add(projectedItem);
      }
      if (isAttachmentCell) {
        projectedFields.put(entry.getKey(), projected);
      }
    }
    return projectedFields;
  }
}
