// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for checkbox/boolean fields. */
public final class FormulaBooleanField implements FormulaField {

  private final String fieldId;

  public FormulaBooleanField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }

  /** Equal to boolean value. Named {@code eq} rather than {@code equals} (§2.3.2). */
  public String eq(boolean value) {
    return value ? isTrue() : isFalse();
  }

  /** Field is checked/true. */
  public String isTrue() {
    return field() + "=TRUE()";
  }

  /** Field is unchecked/false. */
  public String isFalse() {
    return field() + "=FALSE()";
  }
}
