// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Base interface for all formula field types. Provides field reference and empty/not-empty checks.
 */
public interface FormulaField {

  String getFieldId();

  /** Airtable field reference: {@code {fieldId}}. */
  default String field() {
    return "{" + getFieldId() + "}";
  }

  /** Field is blank. */
  default String empty() {
    return field() + "=BLANK()";
  }

  /** Field is not blank. */
  default String notEmpty() {
    return field() + "!=BLANK()";
  }
}
