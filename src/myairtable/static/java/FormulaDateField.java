// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for date fields. */
public final class FormulaDateField implements FormulaField, FormulaDateOperand {

  private final String fieldId;

  public FormulaDateField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }

  @Override
  public String datetimeParseExpr() {
    return "DATETIME_PARSE(" + field() + ")";
  }

  private FormulaDateComparison comparison(String op) {
    return new FormulaDateComparison(fieldId, op);
  }

  /** Date equals. Pass a date string or another date field. */
  public String on(FormulaDateOperand date) {
    return comparison("=").date(date);
  }

  public String on(String date) {
    return on(new FormulaDateLiteral(date));
  }

  /** Returns a {@link FormulaDateComparison} for chaining with time-ago methods. */
  public FormulaDateComparison on() {
    return comparison("=");
  }

  public String notOn(FormulaDateOperand date) {
    return comparison("!=").date(date);
  }

  public String notOn(String date) {
    return notOn(new FormulaDateLiteral(date));
  }

  public FormulaDateComparison notOn() {
    return comparison("!=");
  }

  public String onOrAfter(FormulaDateOperand date) {
    return comparison("<=").date(date);
  }

  public String onOrAfter(String date) {
    return onOrAfter(new FormulaDateLiteral(date));
  }

  public FormulaDateComparison onOrAfter() {
    return comparison("<=");
  }

  public String onOrBefore(FormulaDateOperand date) {
    return comparison(">=").date(date);
  }

  public String onOrBefore(String date) {
    return onOrBefore(new FormulaDateLiteral(date));
  }

  public FormulaDateComparison onOrBefore() {
    return comparison(">=");
  }

  public String after(FormulaDateOperand date) {
    return comparison("<").date(date);
  }

  public String after(String date) {
    return after(new FormulaDateLiteral(date));
  }

  public FormulaDateComparison after() {
    return comparison("<");
  }

  public String before(FormulaDateOperand date) {
    return comparison(">").date(date);
  }

  public String before(String date) {
    return before(new FormulaDateLiteral(date));
  }

  public FormulaDateComparison before() {
    return comparison(">");
  }

  /** Date is between start and end, inclusive. */
  public String between(FormulaDateOperand start, FormulaDateOperand end) {
    return between(start, end, true);
  }

  /** Date is between start and end. */
  public String between(FormulaDateOperand start, FormulaDateOperand end, boolean inclusive) {
    return inclusive
        ? Formulas.and(onOrAfter(start), onOrBefore(end))
        : Formulas.and(after(start), before(end));
  }

  public String between(String start, FormulaDateOperand end) {
    return between(new FormulaDateLiteral(start), end, true);
  }

  public String between(String start, FormulaDateOperand end, boolean inclusive) {
    return between(new FormulaDateLiteral(start), end, inclusive);
  }

  public String between(FormulaDateOperand start, String end) {
    return between(start, new FormulaDateLiteral(end), true);
  }

  public String between(FormulaDateOperand start, String end, boolean inclusive) {
    return between(start, new FormulaDateLiteral(end), inclusive);
  }

  public String between(String start, String end) {
    return between(new FormulaDateLiteral(start), new FormulaDateLiteral(end), true);
  }

  public String between(String start, String end, boolean inclusive) {
    return between(new FormulaDateLiteral(start), new FormulaDateLiteral(end), inclusive);
  }
}
