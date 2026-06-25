// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.BooleanNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.TextNode;
import java.nio.charset.StandardCharsets;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

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

  // ===========================================================================
  // region Truthiness + special values (J8.2 logic)
  // ===========================================================================

  public static JsonNode BLANK() {
    return NullNode.getInstance();
  }

  public static JsonNode TRUE() {
    return BooleanNode.TRUE;
  }

  public static JsonNode FALSE() {
    return BooleanNode.FALSE;
  }

  public static JsonNode IF(JsonNode condition, JsonNode ifTrue, JsonNode ifFalse) {
    if (isTruthy(condition)) {
      return ifTrue == null ? NullNode.getInstance() : ifTrue;
    }
    return ifFalse == null ? NullNode.getInstance() : ifFalse;
  }

  /**
   * SWITCH with the flat-varargs shape the Java transpiler emits: {@code pairs} alternates
   * (pattern, value). The default comes SECOND because Java varargs must be last.
   *
   * <p>Pattern matching uses {@link #S(JsonNode)} coercion (Kotlin parity): the transpiler coerces
   * the expr with {@code V(N(...))} (a {@code DoubleNode}) while whole-number literal patterns emit
   * as {@code V(int)} (an {@code IntNode}), and Jackson's {@code JsonNode.equals} is strict about
   * node types — string-coerced comparison matches across numeric node shapes exactly like the
   * Kotlin/Swift runtimes.
   */
  public static JsonNode SWITCH(JsonNode expr, JsonNode defaultValue, JsonNode... pairs) {
    String key = S(expr);
    for (int i = 0; i + 1 < pairs.length; i += 2) {
      if (S(pairs[i]).equals(key)) {
        return pairs[i + 1] == null ? NullNode.getInstance() : pairs[i + 1];
      }
    }
    return defaultValue == null ? NullNode.getInstance() : defaultValue;
  }

  /** ISERROR returns true for NaN doubles — signals a computation error. */
  public static JsonNode ISERROR(JsonNode value) {
    boolean isNan = value != null && value.isNumber() && Double.isNaN(value.asDouble());
    return BooleanNode.valueOf(isNan);
  }

  public static JsonNode ERROR() {
    // Surface as NaN so ISERROR picks it up.
    return DoubleNode.valueOf(Double.NaN);
  }

  @SuppressWarnings("unused")
  public static JsonNode ERROR(JsonNode message) {
    return ERROR();
  }

  // endregion

  // ===========================================================================
  // region Math functions (J8.2)
  // ===========================================================================

  /** Swift's {@code Double.rounded()}: round half away from zero. */
  private static double roundHalfAwayFromZero(double d) {
    return d >= 0 ? Math.floor(d + 0.5) : Math.ceil(d - 0.5);
  }

  /** Whole-number results emit as integral nodes, mirroring Kotlin's numValue. */
  private static JsonNode numValue(double d) {
    if (Double.isFinite(d) && d == Math.floor(d) && Math.abs(d) < 1e15) {
      return LongNode.valueOf((long) d);
    }
    return DoubleNode.valueOf(d);
  }

  public static JsonNode SUM(JsonNode... args) {
    double total = 0.0;
    for (double n : AN(Arrays.asList(args))) {
      total += n;
    }
    return numValue(total);
  }

  public static JsonNode AVERAGE(JsonNode... args) {
    List<Double> nums = AN(Arrays.asList(args));
    if (nums.isEmpty()) {
      return DoubleNode.valueOf(Double.NaN);
    }
    double total = 0.0;
    for (double n : nums) {
      total += n;
    }
    return numValue(total / nums.size());
  }

  public static JsonNode MIN(JsonNode... args) {
    List<Double> nums = AN(Arrays.asList(args));
    if (nums.isEmpty()) {
      return DoubleNode.valueOf(Double.NaN);
    }
    double m = nums.get(0);
    for (double n : nums) {
      m = Math.min(m, n);
    }
    return numValue(m);
  }

  public static JsonNode MAX(JsonNode... args) {
    List<Double> nums = AN(Arrays.asList(args));
    if (nums.isEmpty()) {
      return DoubleNode.valueOf(Double.NaN);
    }
    double m = nums.get(0);
    for (double n : nums) {
      m = Math.max(m, n);
    }
    return numValue(m);
  }

  public static JsonNode COUNT(JsonNode... args) {
    long c = 0;
    for (JsonNode v : A(Arrays.asList(args))) {
      // Numbers only — strings (even numeric ones) and booleans don't count.
      if (v.isNumber()) {
        c += 1;
      }
    }
    return LongNode.valueOf(c);
  }

  public static JsonNode COUNTA(JsonNode... args) {
    long c = 0;
    for (JsonNode v : A(Arrays.asList(args))) {
      if (v.isNull()) {
        continue;
      }
      if (v.isTextual() && v.asText().isEmpty()) {
        continue;
      }
      c += 1;
    }
    return LongNode.valueOf(c);
  }

  public static JsonNode ROUND(JsonNode value) {
    return ROUND(value, null);
  }

  public static JsonNode ROUND(JsonNode value, JsonNode precision) {
    double n = N(value);
    int p = (int) N(precision);
    double factor = Math.pow(10.0, p);
    return numValue(roundHalfAwayFromZero(n * factor) / factor);
  }

  public static JsonNode ROUNDUP(JsonNode value) {
    return ROUNDUP(value, null);
  }

  public static JsonNode ROUNDUP(JsonNode value, JsonNode precision) {
    double n = N(value);
    int p = (int) N(precision);
    double factor = Math.pow(10.0, p);
    double r = n >= 0 ? Math.ceil(n * factor) / factor : Math.floor(n * factor) / factor;
    return numValue(r);
  }

  public static JsonNode ROUNDDOWN(JsonNode value) {
    return ROUNDDOWN(value, null);
  }

  public static JsonNode ROUNDDOWN(JsonNode value, JsonNode precision) {
    double n = N(value);
    int p = (int) N(precision);
    double factor = Math.pow(10.0, p);
    double r = n >= 0 ? Math.floor(n * factor) / factor : Math.ceil(n * factor) / factor;
    return numValue(r);
  }

  public static JsonNode CEILING(JsonNode value) {
    return CEILING(value, null);
  }

  public static JsonNode CEILING(JsonNode value, JsonNode significance) {
    double n = N(value);
    double s = significance == null ? 1.0 : N(significance);
    double sig = s == 0.0 ? 1.0 : s;
    return numValue(Math.ceil(n / sig) * sig);
  }

  public static JsonNode FLOOR(JsonNode value) {
    return FLOOR(value, null);
  }

  public static JsonNode FLOOR(JsonNode value, JsonNode significance) {
    double n = N(value);
    double s = significance == null ? 1.0 : N(significance);
    double sig = s == 0.0 ? 1.0 : s;
    return numValue(Math.floor(n / sig) * sig);
  }

  public static JsonNode LOG(JsonNode value) {
    return LOG(value, null);
  }

  public static JsonNode LOG(JsonNode value, JsonNode base) {
    double n = N(value);
    if (base != null) {
      return numValue(Math.log(n) / Math.log(N(base)));
    }
    return numValue(Math.log10(n));
  }

  public static JsonNode EVEN(JsonNode value) {
    double n = N(value);
    double c = Math.ceil(Math.abs(n));
    double r = c % 2.0 == 0.0 ? c : c + 1;
    if (n < 0) {
      r = -r;
    }
    return LongNode.valueOf((long) r);
  }

  public static JsonNode ODD(JsonNode value) {
    double n = N(value);
    double c = Math.ceil(Math.abs(n));
    double r = c % 2.0 == 1.0 ? c : c + 1;
    if (n < 0) {
      r = -r;
    }
    return LongNode.valueOf((long) r);
  }

  public static JsonNode VALUE(JsonNode value) {
    if (value == null) {
      return LongNode.valueOf(0);
    }
    String s = S(value);
    if (s.contains(".")) {
      try {
        return DoubleNode.valueOf(Double.parseDouble(s));
      } catch (NumberFormatException ignored) {
        // fall through to NaN
      }
    } else {
      try {
        return LongNode.valueOf(Long.parseLong(s));
      } catch (NumberFormatException ignored) {
        // fall through to NaN
      }
    }
    return DoubleNode.valueOf(Double.NaN);
  }

  public static JsonNode POWER(JsonNode base, JsonNode exp) {
    return numValue(Math.pow(N(base), N(exp)));
  }

  public static JsonNode MOD(JsonNode value, JsonNode divisor) {
    double d = N(divisor);
    if (d == 0.0) {
      return DoubleNode.valueOf(Double.NaN);
    }
    return numValue(N(value) % d);
  }

  public static JsonNode ABS(JsonNode value) {
    return numValue(Math.abs(N(value)));
  }

  public static JsonNode EXP(JsonNode value) {
    double n = N(value);
    // JVM Math.exp(1.0) is one ULP above Math.E (2.7182818284590455 vs
    // ...45); V8 — and therefore Airtable — returns the correctly-rounded
    // E. Pin the integer-1 case so local evaluation matches the API.
    return numValue(n == 1.0 ? Math.E : Math.exp(n));
  }

  public static JsonNode SQRT(JsonNode value) {
    return numValue(Math.sqrt(N(value)));
  }

  public static JsonNode INT(JsonNode value) {
    return LongNode.valueOf((long) Math.floor(N(value)));
  }

  // endregion

  // ===========================================================================
  // region String functions (J8.3)
  // ===========================================================================
  //
  // String positions/lengths count Unicode code points (Swift counts grapheme
  // clusters; code points are the closest JVM analog and match the Rust target).

  private static int cpLength(String s) {
    return s.codePointCount(0, s.length());
  }

  private static int cpIndex(String s, int cpOffset) {
    return s.offsetByCodePoints(0, cpOffset);
  }

  public static JsonNode LEN(JsonNode value) {
    return LongNode.valueOf(cpLength(S(value)));
  }

  public static JsonNode LEFT(JsonNode text, JsonNode count) {
    String s = S(text);
    int n = Math.max(0, (int) N(count));
    int end = cpIndex(s, Math.min(n, cpLength(s)));
    return TextNode.valueOf(s.substring(0, end));
  }

  public static JsonNode RIGHT(JsonNode text, JsonNode count) {
    String s = S(text);
    int n = Math.max(0, (int) N(count));
    int total = cpLength(s);
    int start = cpIndex(s, total - Math.min(n, total));
    return TextNode.valueOf(s.substring(start));
  }

  public static JsonNode MID(JsonNode text, JsonNode start, JsonNode count) {
    String s = S(text);
    int startIdx = Math.max(0, (int) N(start) - 1);
    int len = Math.max(0, (int) N(count));
    int total = cpLength(s);
    if (startIdx >= total) {
      return TextNode.valueOf("");
    }
    int begin = cpIndex(s, startIdx);
    int end = cpIndex(s, Math.min(startIdx + len, total));
    return TextNode.valueOf(s.substring(begin, end));
  }

  public static JsonNode FIND(JsonNode needle, JsonNode haystack) {
    return FIND(needle, haystack, null);
  }

  public static JsonNode FIND(JsonNode needle, JsonNode haystack, JsonNode start) {
    String hay = S(haystack);
    String nee = S(needle);
    int offset = start == null ? 0 : Math.max(0, (int) N(start) - 1);
    if (offset >= cpLength(hay)) {
      return LongNode.valueOf(0);
    }
    int idx = hay.indexOf(nee, cpIndex(hay, offset));
    if (idx < 0) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(hay.codePointCount(0, idx) + 1);
  }

  public static JsonNode SEARCH(JsonNode needle, JsonNode haystack) {
    return SEARCH(needle, haystack, null);
  }

  public static JsonNode SEARCH(JsonNode needle, JsonNode haystack, JsonNode start) {
    String hay = S(haystack).toLowerCase(Locale.ROOT);
    String nee = S(needle).toLowerCase(Locale.ROOT);
    int offset = start == null ? 0 : Math.max(0, (int) N(start) - 1);
    if (offset >= cpLength(hay)) {
      return LongNode.valueOf(0);
    }
    int idx = hay.indexOf(nee, cpIndex(hay, offset));
    if (idx < 0) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(hay.codePointCount(0, idx) + 1);
  }

  public static JsonNode SUBSTITUTE(JsonNode text, JsonNode oldText, JsonNode newText) {
    return SUBSTITUTE(text, oldText, newText, null);
  }

  public static JsonNode SUBSTITUTE(
      JsonNode text, JsonNode oldText, JsonNode newText, JsonNode occurrence) {
    String s = S(text);
    String o = S(oldText);
    String n = S(newText);
    if (o.isEmpty()) {
      return TextNode.valueOf(s);
    }
    if (occurrence == null) {
      return TextNode.valueOf(s.replace(o, n));
    }
    // Replace only the Nth occurrence.
    int target = (int) N(occurrence);
    int current = 1;
    int searchFrom = 0;
    while (true) {
      int idx = s.indexOf(o, searchFrom);
      if (idx < 0) {
        break;
      }
      if (current == target) {
        return TextNode.valueOf(s.substring(0, idx) + n + s.substring(idx + o.length()));
      }
      current += 1;
      searchFrom = idx + 1;
    }
    return TextNode.valueOf(s);
  }

  public static JsonNode REPLACE(
      JsonNode text, JsonNode start, JsonNode count, JsonNode replacement) {
    String s = S(text);
    int startIdx = Math.max(0, (int) N(start) - 1);
    int len = Math.max(0, (int) N(count));
    String r = S(replacement);
    int total = cpLength(s);
    if (startIdx > total) {
      return TextNode.valueOf(s + r);
    }
    int begin = cpIndex(s, startIdx);
    int end = cpIndex(s, Math.min(startIdx + len, total));
    return TextNode.valueOf(s.substring(0, begin) + r + s.substring(end));
  }

  public static JsonNode LOWER(JsonNode value) {
    return TextNode.valueOf(S(value).toLowerCase(Locale.ROOT));
  }

  public static JsonNode UPPER(JsonNode value) {
    return TextNode.valueOf(S(value).toUpperCase(Locale.ROOT));
  }

  public static JsonNode TRIM(JsonNode value) {
    // String.strip() trims Character.isWhitespace, matching Kotlin's trim().
    return TextNode.valueOf(S(value).strip());
  }

  public static JsonNode REPT(JsonNode text, JsonNode count) {
    String s = S(text);
    int n = Math.max(0, (int) N(count));
    return TextNode.valueOf(s.repeat(n));
  }

  public static JsonNode CONCATENATE(JsonNode... args) {
    StringBuilder out = new StringBuilder();
    for (JsonNode arg : args) {
      out.append(S(arg));
    }
    return TextNode.valueOf(out.toString());
  }

  /** Non-alphanumerics left literal by JS {@code encodeURIComponent} (Airtable matches it). */
  private static final String URL_QUERY_ALLOWED_EXTRA = "-_.!~*'()";

  public static JsonNode ENCODE_URL_COMPONENT(JsonNode value) {
    String s = S(value);
    StringBuilder out = new StringBuilder();
    for (byte byteVal : s.getBytes(StandardCharsets.UTF_8)) {
      int b = byteVal & 0xFF;
      char c = (char) b;
      if (b < 0x80 && (Character.isLetterOrDigit(c) || URL_QUERY_ALLOWED_EXTRA.indexOf(c) >= 0)) {
        out.append(c);
      } else {
        out.append('%').append(String.format("%02X", b));
      }
    }
    return TextNode.valueOf(out.toString());
  }

  public static JsonNode T(JsonNode value) {
    if (value != null && value.isTextual()) {
      return TextNode.valueOf(value.asText());
    }
    return TextNode.valueOf("");
  }

  // endregion

  // ===========================================================================
  // region Date/time functions (J8.4)
  // ===========================================================================

  private static final DateTimeFormatter ISO_FORMATTER =
      DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.ROOT)
          .withZone(ZoneOffset.UTC);

  private static String iso(Instant d) {
    return ISO_FORMATTER.format(d);
  }

  private static ZonedDateTime utc(Instant d) {
    return d.atZone(ZoneOffset.UTC);
  }

  private static boolean isWorkingDay(ZonedDateTime z) {
    return z.getDayOfWeek() != DayOfWeek.SATURDAY && z.getDayOfWeek() != DayOfWeek.SUNDAY;
  }

  public static JsonNode NOW() {
    return TextNode.valueOf(iso(Instant.now()));
  }

  public static JsonNode TODAY() {
    ZoneId zone = ZoneId.systemDefault();
    Instant d = LocalDate.now(zone).atStartOfDay(zone).toInstant();
    return TextNode.valueOf(iso(d));
  }

  public static JsonNode YEAR(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getYear());
  }

  public static JsonNode MONTH(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getMonthValue());
  }

  public static JsonNode DAY(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getDayOfMonth());
  }

  public static JsonNode HOUR(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getHour());
  }

  public static JsonNode MINUTE(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getMinute());
  }

  public static JsonNode SECOND(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    return LongNode.valueOf(utc(d).getSecond());
  }

  public static JsonNode WEEKDAY(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    // Airtable: Sunday=0, Monday=1, ..., Saturday=6.
    // java.time DayOfWeek.value is 1 (Monday) ... 7 (Sunday).
    return LongNode.valueOf(utc(d).getDayOfWeek().getValue() % 7);
  }

  public static JsonNode DATETIME_DIFF(JsonNode d1v, JsonNode d2v) {
    return DATETIME_DIFF(d1v, d2v, null);
  }

  public static JsonNode DATETIME_DIFF(JsonNode d1v, JsonNode d2v, JsonNode unit) {
    Instant d1 = D(d1v);
    if (d1 == null) {
      return LongNode.valueOf(0);
    }
    Instant d2 = D(d2v);
    if (d2 == null) {
      return LongNode.valueOf(0);
    }
    double diffSecs = (d1.toEpochMilli() - d2.toEpochMilli()) / 1000.0;
    double v;
    switch (S(unit).toLowerCase(Locale.ROOT)) {
      case "milliseconds" -> v = diffSecs * 1000;
      case "seconds" -> v = diffSecs;
      case "minutes" -> v = diffSecs / 60;
      case "hours" -> v = diffSecs / 3600;
      case "weeks" -> v = diffSecs / (86400.0 * 7);
      case "months" -> {
        ZonedDateTime z1 = utc(d1);
        ZonedDateTime z2 = utc(d2);
        return LongNode.valueOf(
            (z1.getYear() - z2.getYear()) * 12L + (z1.getMonthValue() - z2.getMonthValue()));
      }
      case "years" -> {
        return LongNode.valueOf((long) utc(d1).getYear() - utc(d2).getYear());
      }
      default -> v = diffSecs / 86400; // "days" and unknown units
    }
    return LongNode.valueOf((long) v);
  }

  public static JsonNode DATEADD(JsonNode date, JsonNode count, JsonNode unit) {
    Instant d = D(date);
    if (d == null) {
      return NullNode.getInstance();
    }
    long n = (long) N(count);
    ZonedDateTime z = utc(d);
    ZonedDateTime result =
        switch (S(unit).toLowerCase(Locale.ROOT)) {
          case "years" -> z.plusYears(n);
          case "months" -> z.plusMonths(n);
          case "weeks" -> z.plusWeeks(n);
          case "hours" -> z.plusHours(n);
          case "minutes" -> z.plusMinutes(n);
          case "seconds" -> z.plusSeconds(n);
          default -> z.plusDays(n); // "days" and unknown units
        };
    return TextNode.valueOf(iso(result.toInstant()));
  }

  public static JsonNode IS_SAME(JsonNode d1, JsonNode d2) {
    return IS_SAME(d1, d2, null);
  }

  public static JsonNode IS_SAME(JsonNode d1, JsonNode d2, JsonNode unit) {
    JsonNode u = unit == null ? TextNode.valueOf("days") : unit;
    JsonNode v = DATETIME_DIFF(d1, d2, u);
    return BooleanNode.valueOf(v.asLong() == 0L);
  }

  public static JsonNode IS_BEFORE(JsonNode d1, JsonNode d2) {
    return IS_BEFORE(d1, d2, null);
  }

  public static JsonNode IS_BEFORE(JsonNode d1, JsonNode d2, JsonNode unit) {
    JsonNode u = unit == null ? TextNode.valueOf("days") : unit;
    JsonNode v = DATETIME_DIFF(d1, d2, u);
    return BooleanNode.valueOf(v.asLong() < 0L);
  }

  public static JsonNode IS_AFTER(JsonNode d1, JsonNode d2) {
    return IS_AFTER(d1, d2, null);
  }

  public static JsonNode IS_AFTER(JsonNode d1, JsonNode d2, JsonNode unit) {
    JsonNode u = unit == null ? TextNode.valueOf("days") : unit;
    JsonNode v = DATETIME_DIFF(d1, d2, u);
    return BooleanNode.valueOf(v.asLong() > 0L);
  }

  private static String plural(long n, String unit) {
    return n + " " + unit + (n == 1L ? "" : "s");
  }

  /** Human-friendly duration string between two dates. */
  private static String humanDuration(JsonNode d1v, JsonNode d2v) {
    Instant d1 = D(d1v);
    if (d1 == null) {
      return "";
    }
    Instant d2 = D(d2v);
    if (d2 == null) {
      return "";
    }
    long diff = Math.abs((long) ((d1.toEpochMilli() - d2.toEpochMilli()) / 1000.0));
    long minutes = diff / 60;
    long hours = minutes / 60;
    long days = hours / 24;
    ZonedDateTime z1 = utc(d1);
    ZonedDateTime z2 = utc(d2);
    long months =
        Math.abs((z1.getYear() - z2.getYear()) * 12L + (z1.getMonthValue() - z2.getMonthValue()));
    long years = months / 12;
    if (years > 0) {
      return plural(years, "year");
    }
    if (months > 0) {
      return plural(months, "month");
    }
    if (days > 0) {
      return plural(days, "day");
    }
    if (hours > 0) {
      return plural(hours, "hour");
    }
    if (minutes > 0) {
      return plural(minutes, "minute");
    }
    return plural(diff, "second");
  }

  public static JsonNode TONOW(JsonNode date) {
    return TONOW(date, null);
  }

  public static JsonNode TONOW(JsonNode date, JsonNode unit) {
    if (unit != null) {
      return DATETIME_DIFF(NOW(), date, unit);
    }
    return TextNode.valueOf(humanDuration(date, NOW()));
  }

  public static JsonNode FROMNOW(JsonNode date) {
    return FROMNOW(date, null);
  }

  public static JsonNode FROMNOW(JsonNode date, JsonNode unit) {
    if (unit != null) {
      return DATETIME_DIFF(date, NOW(), unit);
    }
    return TextNode.valueOf(humanDuration(date, NOW()));
  }

  private static final Map<String, DayOfWeek> WEEKNUM_START_DAYS =
      Map.of(
          "sunday", DayOfWeek.SUNDAY,
          "monday", DayOfWeek.MONDAY,
          "tuesday", DayOfWeek.TUESDAY,
          "wednesday", DayOfWeek.WEDNESDAY,
          "thursday", DayOfWeek.THURSDAY,
          "friday", DayOfWeek.FRIDAY,
          "saturday", DayOfWeek.SATURDAY);

  public static JsonNode WEEKNUM(JsonNode date) {
    return WEEKNUM(date, null);
  }

  /** Week number of the year (week starts on the supplied day; default Sunday). */
  public static JsonNode WEEKNUM(JsonNode date, JsonNode startDay) {
    Instant d = D(date);
    if (d == null) {
      return LongNode.valueOf(0);
    }
    DayOfWeek first =
        WEEKNUM_START_DAYS.getOrDefault(S(startDay).toLowerCase(Locale.ROOT), DayOfWeek.SUNDAY);
    // Minimal days in first week = 1, matching Apple's gregorian Calendar default.
    WeekFields weekFields = WeekFields.of(first, 1);
    return LongNode.valueOf(utc(d).get(weekFields.weekOfYear()));
  }

  /** WORKDAY advances a date by N working days (Mon–Fri). */
  public static JsonNode WORKDAY(JsonNode start, JsonNode numDays) {
    Instant d = D(start);
    if (d == null) {
      return NullNode.getInstance();
    }
    ZonedDateTime z = utc(d);
    int remaining = (int) N(numDays);
    long direction = remaining >= 0 ? 1L : -1L;
    remaining = Math.abs(remaining);
    while (remaining > 0) {
      z = z.plusDays(direction);
      if (isWorkingDay(z)) {
        remaining -= 1;
      }
    }
    return TextNode.valueOf(iso(z.toInstant()));
  }

  /** Count working days (Mon–Fri) between two dates. Signed (start later → negative). */
  public static JsonNode WORKDAY_DIFF(JsonNode start, JsonNode end) {
    Instant d1 = D(start);
    if (d1 == null) {
      return LongNode.valueOf(0);
    }
    Instant d2 = D(end);
    if (d2 == null) {
      return LongNode.valueOf(0);
    }
    long count = 0;
    ZonedDateTime current = utc(d1);
    int direction = d2.isAfter(d1) ? 1 : -1;
    if (isWorkingDay(current)) {
      count += direction;
    }
    while ((direction == 1 && current.toInstant().isBefore(d2))
        || (direction == -1 && current.toInstant().isAfter(d2))) {
      current = current.plusDays(direction);
      if (isWorkingDay(current)) {
        count += direction;
      }
    }
    return LongNode.valueOf(count);
  }

  /**
   * Reinterpret a datetime in a different timezone. Returns the wall-clock value as an ISO string
   * (matching the Python runtime's behavior).
   */
  public static JsonNode SET_TIMEZONE(JsonNode date, JsonNode tz) {
    Instant d = D(date);
    if (d == null) {
      return NullNode.getInstance();
    }
    ZoneId zone;
    try {
      zone = ZoneId.of(S(tz));
    } catch (Exception e) {
      return TextNode.valueOf(iso(d));
    }
    // Offset the UTC instant so the "clock face" matches the target zone.
    int offset = zone.getRules().getOffset(d).getTotalSeconds();
    return TextNode.valueOf(iso(d.plusSeconds(offset)));
  }

  public static JsonNode DATETIME_FORMAT(JsonNode date) {
    return DATETIME_FORMAT(date, null);
  }

  public static JsonNode DATETIME_FORMAT(JsonNode date, JsonNode fmt) {
    Instant d = D(date);
    if (d == null) {
      return TextNode.valueOf("");
    }
    if (fmt == null) {
      return TextNode.valueOf(iso(d));
    }
    // Moment.js → DateTimeFormatter token mapping.
    String pattern = S(fmt).replace("YYYY", "yyyy").replace("YY", "yy").replace("DD", "dd");
    try {
      return TextNode.valueOf(
          DateTimeFormatter.ofPattern(pattern, Locale.US).withZone(ZoneOffset.UTC).format(d));
    } catch (Exception e) {
      return TextNode.valueOf(iso(d));
    }
  }

  public static JsonNode DATESTR(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return TextNode.valueOf("");
    }
    return TextNode.valueOf(
        DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT).withZone(ZoneOffset.UTC).format(d));
  }

  public static JsonNode TIMESTR(JsonNode value) {
    Instant d = D(value);
    if (d == null) {
      return TextNode.valueOf("");
    }
    return TextNode.valueOf(
        DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT).withZone(ZoneOffset.UTC).format(d));
  }

  public static JsonNode DATETIME_PARSE(JsonNode value) {
    return DATETIME_PARSE(value, null);
  }

  @SuppressWarnings("unused")
  public static JsonNode DATETIME_PARSE(JsonNode value, JsonNode fmt) {
    // Input-format override is ignored — we try ISO 8601 then a few fallbacks.
    Instant d = D(value);
    if (d == null) {
      return NullNode.getInstance();
    }
    return TextNode.valueOf(iso(d));
  }

  // endregion

  // ===========================================================================
  // region Array functions (J8.5)
  // ===========================================================================

  public static JsonNode ARRAYJOIN(JsonNode arr) {
    return ARRAYJOIN(arr, null);
  }

  public static JsonNode ARRAYJOIN(JsonNode arr, JsonNode separator) {
    String sep = separator == null ? ", " : S(separator);
    if (arr == null) {
      return TextNode.valueOf("");
    }
    if (arr.isArray()) {
      StringBuilder out = new StringBuilder();
      boolean firstItem = true;
      for (JsonNode v : arr) {
        if (!firstItem) {
          out.append(sep);
        }
        out.append(S(v));
        firstItem = false;
      }
      return TextNode.valueOf(out.toString());
    }
    return TextNode.valueOf(S(arr));
  }

  public static JsonNode ARRAYUNIQUE(JsonNode arr) {
    ArrayNode out = AirtableJson.MAPPER.createArrayNode();
    if (arr == null) {
      return out;
    }
    if (!arr.isArray()) {
      out.add(arr);
      return out;
    }
    List<JsonNode> seen = new ArrayList<>();
    for (JsonNode v : arr) {
      if (!seen.contains(v)) {
        seen.add(v);
        out.add(v);
      }
    }
    return out;
  }

  public static JsonNode ARRAYCOMPACT(JsonNode arr) {
    ArrayNode out = AirtableJson.MAPPER.createArrayNode();
    if (arr == null) {
      return out;
    }
    if (!arr.isArray()) {
      out.add(arr);
      return out;
    }
    for (JsonNode v : arr) {
      if (v.isNull()) {
        continue;
      }
      if (v.isTextual() && v.asText().isEmpty()) {
        continue;
      }
      out.add(v);
    }
    return out;
  }

  public static JsonNode ARRAYFLATTEN(JsonNode arr) {
    ArrayNode out = AirtableJson.MAPPER.createArrayNode();
    if (arr == null) {
      return out;
    }
    if (!arr.isArray()) {
      out.add(arr);
      return out;
    }
    flattenInto(arr, out);
    return out;
  }

  private static void flattenInto(JsonNode xs, ArrayNode out) {
    for (JsonNode x : xs) {
      if (x.isArray()) {
        flattenInto(x, out);
      } else {
        out.add(x);
      }
    }
  }

  // endregion

  // ===========================================================================
  // region Regex (J8.6)
  // ===========================================================================

  public static JsonNode REGEX_EXTRACT(JsonNode text, JsonNode pattern) {
    String s = S(text);
    Pattern re;
    try {
      re = Pattern.compile(S(pattern));
    } catch (PatternSyntaxException e) {
      return TextNode.valueOf("");
    }
    Matcher m = re.matcher(s);
    if (!m.find()) {
      return TextNode.valueOf("");
    }
    return TextNode.valueOf(m.group());
  }

  public static JsonNode REGEX_MATCH(JsonNode text, JsonNode pattern) {
    String s = S(text);
    Pattern re;
    try {
      re = Pattern.compile(S(pattern));
    } catch (PatternSyntaxException e) {
      return BooleanNode.valueOf(false);
    }
    return BooleanNode.valueOf(re.matcher(s).find());
  }

  public static JsonNode REGEX_REPLACE(JsonNode text, JsonNode pattern, JsonNode replacement) {
    String s = S(text);
    String r = S(replacement);
    Pattern re;
    try {
      re = Pattern.compile(S(pattern));
    } catch (PatternSyntaxException e) {
      return TextNode.valueOf(s);
    }
    return TextNode.valueOf(re.matcher(s).replaceAll(r));
  }

  // endregion
}
