// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for single-select fields. */
public final class FormulaSingleSelectField implements FormulaTextOps {

  private final String fieldId;

  public FormulaSingleSelectField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }
}
