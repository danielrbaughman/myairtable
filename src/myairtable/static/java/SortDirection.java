// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonValue;

/** Sort direction for Airtable list queries. */
public enum SortDirection {
  ASC("asc"),
  DESC("desc");

  private final String wire;

  SortDirection(String wire) {
    this.wire = wire;
  }

  /** The wire value ({@code "asc"} / {@code "desc"}). */
  @JsonValue
  public String wire() {
    return wire;
  }
}
