// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * A single sort clause. Airtable supports multiple sort clauses per query and applies them
 * left-to-right.
 */
public record Sort(String field, SortDirection direction) {

  /** Ascending sort on {@code field}. */
  public Sort(String field) {
    this(field, SortDirection.ASC);
  }
}
