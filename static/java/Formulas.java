// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

/** Top-level formula combinators matching Airtable's logical functions. */
public final class Formulas {

  private Formulas() {}

  /** Combine formulas with AND logic. Empty strings are filtered out. */
  public static String and(String... args) {
    return and(Arrays.asList(args));
  }

  public static String and(List<String> args) {
    List<String> filtered = args.stream().filter(a -> !a.isEmpty()).toList();
    return switch (filtered.size()) {
      case 0 -> "";
      case 1 -> filtered.get(0);
      default -> "AND(" + String.join(",", filtered) + ")";
    };
  }

  /** Combine formulas with OR logic. Empty strings are filtered out. */
  public static String or(String... args) {
    return or(Arrays.asList(args));
  }

  public static String or(List<String> args) {
    List<String> filtered = args.stream().filter(a -> !a.isEmpty()).toList();
    return switch (filtered.size()) {
      case 0 -> "";
      case 1 -> filtered.get(0);
      default -> "OR(" + String.join(",", filtered) + ")";
    };
  }

  /** Negate a formula. */
  public static String not(String formula) {
    return "NOT(" + formula + ")";
  }

  /** Exclusive OR. Empty strings are filtered out. */
  public static String xor(String... args) {
    return xor(Arrays.asList(args));
  }

  public static String xor(List<String> args) {
    List<String> filtered = args.stream().filter(a -> !a.isEmpty()).toList();
    return switch (filtered.size()) {
      case 0 -> "";
      case 1 -> filtered.get(0);
      default -> "XOR(" + String.join(",", filtered) + ")";
    };
  }

  // ---- shared escaping / wrapping helpers (package-private) ----

  /**
   * Escape a value for an Airtable double-quoted formula string. Backslashes are escaped FIRST,
   * then quotes — otherwise a trailing {@code \} leaves the closing quote live and the remainder of
   * the value executes as formula code.
   */
  static String escapeFormulaString(String value) {
    return value.replace("\\", "\\\\").replace("\"", "\\\"");
  }

  /** Escape a value for an Airtable single-quoted formula string. */
  static String escapeFormulaStringSingle(String value) {
    return value.replace("\\", "\\\\").replace("'", "\\'");
  }

  static String wrapField(String field, boolean caseSensitive, boolean trim) {
    String v = field;
    if (trim) {
      v = "TRIM(" + v + ")";
    }
    if (!caseSensitive) {
      v = "LOWER(" + v + ")";
    }
    return v;
  }

  static String wrapValueStr(String value, boolean caseSensitive, boolean trim) {
    String v = "\"" + escapeFormulaString(value) + "\"";
    if (trim) {
      v = "TRIM(" + v + ")";
    }
    if (!caseSensitive) {
      v = "LOWER(" + v + ")";
    }
    return v;
  }

  static String joinMapped(List<String> values, java.util.function.Function<String, String> fn) {
    return values.stream().map(fn).collect(Collectors.joining(","));
  }
}
