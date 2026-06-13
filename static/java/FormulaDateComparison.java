// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Intermediate builder for date "time ago" comparisons. */
public final class FormulaDateComparison {

  private final String fieldId;
  private final String op;

  FormulaDateComparison(String fieldId, String op) {
    this.fieldId = fieldId;
    this.op = op;
  }

  /** Compare against another date field (or any date operand). */
  public String date(FormulaDateOperand other) {
    return other.datetimeParseExpr() + op + "DATETIME_PARSE({" + fieldId + "})";
  }

  /** Compare against a literal date string. */
  public String date(String other) {
    return date(new FormulaDateLiteral(other));
  }

  public String millisecondsAgo(int n) {
    return ago(n, "milliseconds");
  }

  public String secondsAgo(int n) {
    return ago(n, "seconds");
  }

  public String minutesAgo(int n) {
    return ago(n, "minutes");
  }

  public String hoursAgo(int n) {
    return ago(n, "hours");
  }

  public String daysAgo(int n) {
    return ago(n, "days");
  }

  public String weeksAgo(int n) {
    return ago(n, "weeks");
  }

  public String monthsAgo(int n) {
    return ago(n, "months");
  }

  public String quartersAgo(int n) {
    return ago(n, "quarters");
  }

  public String yearsAgo(int n) {
    return ago(n, "years");
  }

  private String ago(int n, String unit) {
    return "DATETIME_DIFF(NOW(),{" + fieldId + "},\"" + unit + "\")" + op + n;
  }
}
