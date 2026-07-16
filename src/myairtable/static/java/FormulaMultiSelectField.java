// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for multi-select fields. */
public final class FormulaMultiSelectField implements FormulaTextOps {

  private final String fieldId;

  public FormulaMultiSelectField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }
}
