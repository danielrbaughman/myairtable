// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Formula builder for {@code multipleLookupValues} / lookup fields.
 *
 * <p>Lookup field values are arrays. Airtable does not auto-coerce arrays through {@code LOWER} /
 * {@code TRIM} / {@code FIND}, so {@code contains}, {@code startsWith} and {@code endsWith} would
 * silently match nothing. {@link #stringField} wraps the reference in {@code ARRAYJOIN(field, ",
 * ")} so string ops see a string.
 *
 * <p>Equality ({@code =}) is unaffected — Airtable coerces array fields to a comma-joined string
 * under {@code =}, so direct equality already works.
 */
public final class FormulaLookupField implements FormulaTextOps {

  private final String fieldId;

  public FormulaLookupField(String fieldId) {
    this.fieldId = fieldId;
  }

  @Override
  public String getFieldId() {
    return fieldId;
  }

  @Override
  public String stringField() {
    return "ARRAYJOIN(" + field() + ", \", \")";
  }
}
