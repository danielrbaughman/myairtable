// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for text fields. */
public final class FormulaTextField implements FormulaTextOps {

  private final String fieldId;

  public FormulaTextField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }
}
