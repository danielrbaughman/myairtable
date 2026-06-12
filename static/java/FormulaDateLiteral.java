// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** A literal date string operand, e.g. {@code "2025-01-15"}. Package-private. */
final class FormulaDateLiteral implements FormulaDateOperand {

  private final String value;

  FormulaDateLiteral(String value) {
    this.value = value;
  }

  @Override
  public String datetimeParseExpr() {
    return "DATETIME_PARSE('" + Formulas.escapeFormulaStringSingle(value) + "')";
  }
}
