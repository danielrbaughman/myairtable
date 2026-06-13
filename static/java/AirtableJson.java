// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

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
}
