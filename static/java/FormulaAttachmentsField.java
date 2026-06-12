// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for attachment fields. */
public final class FormulaAttachmentsField implements FormulaField {

  private final String fieldId;

  public FormulaAttachmentsField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }

  /** Has exactly N attachments. */
  public String count(int n) {
    return "LEN(" + field() + ")=" + n;
  }

  /** Has no attachments. */
  @Override
  public String empty() {
    return "LEN(" + field() + ")=0";
  }

  /** Has attachments. */
  @Override
  public String notEmpty() {
    return "LEN(" + field() + ")>0";
  }
}
