// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Formula builder for number fields. */
public final class FormulaNumberField implements FormulaField {

  private final String fieldId;

  public FormulaNumberField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }

  /** Equal to value. Named {@code eq} rather than {@code equals} (§2.3.2). */
  public String eq(Number value) {
    return field() + "=" + value;
  }

  /** Not equal to value. Named {@code neq} for symmetry with {@code eq} (§2.3.2). */
  public String neq(Number value) {
    return field() + "!=" + value;
  }

  /** Greater than value. */
  public String greaterThan(Number value) {
    return field() + ">" + value;
  }

  /** Less than value. */
  public String lessThan(Number value) {
    return field() + "<" + value;
  }

  /** Greater than or equal to value. */
  public String greaterThanOrEquals(Number value) {
    return field() + ">=" + value;
  }

  /** Less than or equal to value. */
  public String lessThanOrEquals(Number value) {
    return field() + "<=" + value;
  }

  /** Between min and max, inclusive. */
  public String between(Number min, Number max) {
    return between(min, max, true);
  }

  /** Between min and max. */
  public String between(Number min, Number max, boolean inclusive) {
    return inclusive
        ? Formulas.and(greaterThanOrEquals(min), lessThanOrEquals(max))
        : Formulas.and(greaterThan(min), lessThan(max));
  }
}
