// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.List;
import java.util.stream.Collectors;

/** Text operations shared by text, select, and lookup fields. */
public interface FormulaTextOps extends FormulaField {

  /**
   * Field reference used in string operations (FIND/LEN with LOWER/TRIM). Lookup fields override
   * this to wrap the reference in {@code ARRAYJOIN(field, ", ")} so Airtable can coerce the array
   * to a string. Defaults to the bare {@code {field}} reference.
   */
  default String stringField() {
    return field();
  }

  /**
   * Exact equality.
   *
   * <p>Named {@code eq} rather than {@code equals} because {@code equals(value)} would overload
   * {@code Object.equals} and silently resolve to the wrong method (java-plan-v2 §2.3.2).
   */
  default String eq(String value) {
    return eq(value, true, false);
  }

  default String eq(String value, boolean caseSensitive) {
    return eq(value, caseSensitive, false);
  }

  default String eq(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(field(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return f + "=" + v;
  }

  /** Equals any of the given values. */
  default String equalsAny(List<String> values) {
    return equalsAny(values, true, false);
  }

  default String equalsAny(List<String> values, boolean caseSensitive, boolean trim) {
    return Formulas.or(values.stream().map(v -> eq(v, caseSensitive, trim)).toList());
  }

  /** Not equal. Named {@code neq} for symmetry with {@code eq} (§2.3.2). */
  default String neq(String value) {
    return neq(value, true, false);
  }

  default String neq(String value, boolean caseSensitive) {
    return neq(value, caseSensitive, false);
  }

  default String neq(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(field(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return f + "!=" + v;
  }

  /** Contains substring. */
  default String contains(String value) {
    return contains(value, true, false);
  }

  default String contains(String value, boolean caseSensitive) {
    return contains(value, caseSensitive, false);
  }

  default String contains(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(stringField(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return "FIND(" + v + "," + f + ")>0";
  }

  /** Contains any of the given values. */
  default String containsAny(List<String> values) {
    return containsAny(values, true, false);
  }

  default String containsAny(List<String> values, boolean caseSensitive, boolean trim) {
    return Formulas.or(values.stream().map(v -> contains(v, caseSensitive, trim)).toList());
  }

  /** Contains all of the given values. */
  default String containsAll(List<String> values) {
    return containsAll(values, true, false);
  }

  default String containsAll(List<String> values, boolean caseSensitive, boolean trim) {
    return Formulas.and(values.stream().map(v -> contains(v, caseSensitive, trim)).toList());
  }

  /** Does not contain substring. */
  default String notContains(String value) {
    return notContains(value, true, false);
  }

  default String notContains(String value, boolean caseSensitive, boolean trim) {
    return Formulas.not(contains(value, caseSensitive, trim));
  }

  /** Starts with the given value. */
  default String startsWith(String value) {
    return startsWith(value, true, false);
  }

  default String startsWith(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(stringField(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return "FIND(" + v + "," + f + ")=1";
  }

  /** Does not start with the given value. */
  default String notStartsWith(String value) {
    return notStartsWith(value, true, false);
  }

  default String notStartsWith(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(stringField(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return "FIND(" + v + "," + f + ")!=1";
  }

  /** Ends with the given value. */
  default String endsWith(String value) {
    return endsWith(value, true, false);
  }

  default String endsWith(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(stringField(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return "FIND(" + v + "," + f + ")=LEN(" + f + ")-LEN(" + v + ")+1";
  }

  /** Does not end with the given value. */
  default String notEndsWith(String value) {
    return notEndsWith(value, true, false);
  }

  default String notEndsWith(String value, boolean caseSensitive, boolean trim) {
    String f = Formulas.wrapField(stringField(), caseSensitive, trim);
    String v = Formulas.wrapValueStr(value, caseSensitive, trim);
    return "FIND(" + v + "," + f + ")!=LEN(" + f + ")-LEN(" + v + ")+1";
  }

  /** Phone number equality (strips spaces, dashes, parens, plus, dots). */
  default String phoneEquals(String value) {
    String normalized =
        value
            .chars()
            .filter(c -> " -().+".indexOf(c) < 0)
            .mapToObj(c -> String.valueOf((char) c))
            .collect(Collectors.joining());
    String stripped =
        "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE("
            + field()
            + ",\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")";
    return stripped + "=\"" + Formulas.escapeFormulaString(normalized) + "\"";
  }

  /** Regex match. */
  default String regexMatch(String pattern) {
    // Escape for the formula-string context only; regex escapes like \d become
    // \\d in the formula source, which Airtable's parser unescapes back before
    // handing the pattern to the regex engine.
    return "REGEX_MATCH(" + field() + ",\"" + Formulas.escapeFormulaString(pattern) + "\")";
  }
}
