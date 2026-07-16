// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Either side of a date comparison: a literal date string or another date field. String literals
 * are accepted via dedicated overloads on {@link FormulaDateComparison} and {@link
 * FormulaDateField}.
 */
public interface FormulaDateOperand {
  /** The operand wrapped in {@code DATETIME_PARSE(...)} for comparison. */
  String datetimeParseExpr();
}
