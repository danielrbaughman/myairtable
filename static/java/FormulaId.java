// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.List;

/** Formula builder for record IDs. */
public final class FormulaId {

  /** Match a specific record ID. */
  public String eq(String id) {
    return "RECORD_ID()='" + Formulas.escapeFormulaStringSingle(id) + "'";
  }

  /** Match any of the given record IDs. */
  public String inList(List<String> ids) {
    return switch (ids.size()) {
      case 0 -> "FALSE()";
      case 1 -> eq(ids.get(0));
      default -> Formulas.or(ids.stream().map(this::eq).toList());
    };
  }
}
