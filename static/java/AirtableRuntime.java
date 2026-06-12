// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * The formula runtime: value coercion plus (as of J-F8) the ~80 Airtable formula functions.
 *
 * <p>The runtime operates on Jackson {@link JsonNode} — the analog of kotlinx's {@code JsonElement}
 * and Swift's {@code AirtableJSONValue}. Unlike Kotlin (top-level functions), Java has no top-level
 * functions, so ALL coercion helpers live here as statics and the transpiler emits qualified {@code
 * AirtableRuntime.X(...)} calls (java-plan-v2 §2.3.3).
 *
 * <p>Method names deliberately use the cross-language runtime naming shared with the
 * Rust/Swift/Kotlin targets; the formula transpiler emits calls to these exact names.
 */
public final class AirtableRuntime {

  private AirtableRuntime() {}

  // ===========================================================================
  // region Runtime value coercion
  // ===========================================================================

  /**
   * Convert any value to {@link JsonNode} for runtime composition. Used by the transpiler to wrap
   * model field references (e.g. {@code AirtableRuntime.V(this.numberInt)}). {@code null} inputs
   * produce {@link NullNode}; unserializable values degrade to {@link NullNode} rather than
   * throwing inside a formula evaluation (matches the Swift/Kotlin targets).
   */
  public static JsonNode V(Object value) {
    if (value == null) {
      return NullNode.getInstance();
    }
    if (value instanceof JsonNode node) {
      return node;
    }
    if (value instanceof Instant instant) {
      // Dates compose into formulas as ISO 8601 strings (matches Swift/Kotlin).
      return TextNode.valueOf(instant.toString());
    }
    if (value instanceof Duration duration) {
      // Durations compose as numeric seconds — the Airtable wire form.
      return DoubleNode.valueOf(duration.getSeconds() + duration.getNano() / 1_000_000_000.0);
    }
    try {
      return AirtableJson.MAPPER.valueToTree(value);
    } catch (IllegalArgumentException e) {
      return NullNode.getInstance();
    }
  }

  /** Coerce to {@code double}. Mirrors Airtable's numeric coercion rules. */
  public static double N(JsonNode value) {
    if (value == null || value.isNull() || value.isMissingNode()) {
      return 0.0;
    }
    if (value.isTextual()) {
      try {
        return Double.parseDouble(value.asText().trim());
      } catch (NumberFormatException e) {
        return 0.0;
      }
    }
    if (value.isBoolean()) {
      return value.asBoolean() ? 1.0 : 0.0;
    }
    if (value.isNumber()) {
      return value.asDouble();
    }
    if (value.isArray()) {
      return value.isEmpty() ? 0.0 : N(value.get(0));
    }
    return 0.0;
  }

  /** Coerce to {@link String}. Airtable strips {@code .0} from whole-number floats. */
  public static String S(JsonNode value) {
    if (value == null || value.isNull() || value.isMissingNode()) {
      return "";
    }
    if (value.isTextual()) {
      return value.asText();
    }
    if (value.isBoolean()) {
      return value.asBoolean() ? "1" : "0";
    }
    if (value.isIntegralNumber()) {
      return Long.toString(value.asLong());
    }
    if (value.isNumber()) {
      double d = value.asDouble();
      if (Double.isFinite(d) && d == Math.floor(d) && Math.abs(d) < 1e15) {
        return Long.toString((long) d);
      }
      return Double.toString(d);
    }
    if (value.isArray()) {
      return value.isEmpty() ? "" : S(value.get(0));
    }
    return "";
  }

  /** Flatten args into a single {@code List<JsonNode>} (one level; Java {@code null}s dropped). */
  public static List<JsonNode> A(List<JsonNode> args) {
    List<JsonNode> result = new ArrayList<>();
    for (JsonNode arg : args) {
      if (arg == null) {
        continue;
      }
      if (arg.isArray()) {
        arg.forEach(result::add);
      } else {
        result.add(arg);
      }
    }
    return result;
  }

  /** Flatten + coerce to numbers. */
  public static List<Double> AN(List<JsonNode> args) {
    List<Double> result = new ArrayList<>();
    for (JsonNode node : A(args)) {
      result.add(N(node));
    }
    return result;
  }

  /** Flatten + coerce to strings. */
  public static List<String> AS(List<JsonNode> args) {
    List<String> result = new ArrayList<>();
    for (JsonNode node : A(args)) {
      result.add(S(node));
    }
    return result;
  }

  /** Coerce to {@link Instant}. ISO 8601 strings, Unix timestamps, or {@code null}. */
  public static Instant D(JsonNode value) {
    if (value == null || value.isNull() || value.isMissingNode()) {
      return null;
    }
    if (value.isTextual()) {
      return AirtableDateParser.parse(value.asText());
    }
    if (value.isNumber()) {
      return Instant.ofEpochMilli((long) (value.asDouble() * 1000));
    }
    if (value.isArray()) {
      return value.isEmpty() ? null : D(value.get(0));
    }
    return null;
  }

  /** Airtable truthiness: null/0/NaN/""/empty array/empty object are falsy. */
  public static boolean isTruthy(JsonNode value) {
    if (value == null || value.isNull() || value.isMissingNode()) {
      return false;
    }
    if (value.isTextual()) {
      return !value.asText().isEmpty();
    }
    if (value.isBoolean()) {
      return value.asBoolean();
    }
    if (value.isNumber()) {
      double d = value.asDouble();
      return d != 0.0 && !Double.isNaN(d);
    }
    if (value.isArray() || value.isObject()) {
      return !value.isEmpty();
    }
    return false;
  }

  // endregion
}
