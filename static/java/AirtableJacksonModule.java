// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeFormatter;

/**
 * Jackson module for the Airtable wire format: {@link Instant} via the 3-format {@link
 * AirtableDateParser}, {@link Duration} as <b>numeric seconds</b> (locked by Swift/Kotlin live
 * verification — NOT ISO-8601 {@code PT30S}).
 *
 * <p>Deliberately replaces {@code jackson-datatype-jsr310}: that module must NOT be on the
 * classpath / registered (its Duration serializer would shadow this one). Never call {@code
 * findAndRegisterModules()} (java-plan-v2 §2.3.6).
 */
public final class AirtableJacksonModule extends SimpleModule {

  public AirtableJacksonModule() {
    super("AirtableJacksonModule");
    addSerializer(Instant.class, new AirtableInstantSerializer());
    addDeserializer(Instant.class, new AirtableInstantDeserializer());
    addSerializer(Duration.class, new AirtableDurationSerializer());
    addDeserializer(Duration.class, new AirtableDurationDeserializer());
  }

  /** Encodes as ISO-8601 UTC ({@code 2024-01-15T10:30:00Z}). */
  static final class AirtableInstantSerializer extends JsonSerializer<Instant> {
    @Override
    public void serialize(Instant value, JsonGenerator gen, SerializerProvider provider)
        throws IOException {
      gen.writeString(DateTimeFormatter.ISO_INSTANT.format(value));
    }
  }

  /** Decodes via {@link AirtableDateParser} (fractional ISO → offset ISO → date-only). */
  static final class AirtableInstantDeserializer extends JsonDeserializer<Instant> {
    @Override
    public Instant deserialize(JsonParser p, DeserializationContext ctxt) throws IOException {
      String text = p.getValueAsString();
      Instant parsed = AirtableDateParser.parse(text);
      if (parsed == null) {
        throw new IOException("Cannot parse Airtable date: \"" + text + "\"");
      }
      return parsed;
    }
  }

  /** Encodes as numeric seconds (whole seconds as integer, fractional as double). */
  static final class AirtableDurationSerializer extends JsonSerializer<Duration> {
    @Override
    public void serialize(Duration value, JsonGenerator gen, SerializerProvider provider)
        throws IOException {
      if (value.getNano() == 0) {
        gen.writeNumber(value.getSeconds());
      } else {
        gen.writeNumber(value.getSeconds() + value.getNano() / 1_000_000_000.0);
      }
    }
  }

  /** Decodes from numeric seconds. */
  static final class AirtableDurationDeserializer extends JsonDeserializer<Duration> {
    @Override
    public Duration deserialize(JsonParser p, DeserializationContext ctxt) throws IOException {
      double seconds = p.getValueAsDouble();
      return Duration.ofNanos(Math.round(seconds * 1_000_000_000.0));
    }
  }
}
