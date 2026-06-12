// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.util.ArrayList;
import java.util.List;

/**
 * Query parameters for Airtable list-records requests.
 *
 * <p>Immutable; idiomatic Java construction is the fluent wither chain:
 *
 * <pre>{@code
 * new AirtableQuery()
 *     .withFormula("NOT({Name}=BLANK())")
 *     .withMaxRecords(10)
 *     .withSort("Name", SortDirection.DESC)
 * }</pre>
 */
public final class AirtableQuery {

  /** Cell format for list queries. */
  public enum CellFormat {
    JSON("json"),
    STRING("string");

    private final String wire;

    CellFormat(String wire) {
      this.wire = wire;
    }

    public String wire() {
      return wire;
    }
  }

  /** A single query parameter; keys can repeat ({@code fields[]}, {@code sort[i][...]}). */
  public record Param(String name, String value) {}

  private final String formula;
  private final List<Sort> sort;
  private final List<String> fields;
  private final Integer maxRecords;
  private final Integer pageSize;
  private final String view;
  private final boolean returnFieldsByFieldId;
  private final CellFormat cellFormat;
  private final String timeZone;
  private final String userLocale;

  /** The default query: no filter, ID-keyed fields, JSON cell format. */
  public AirtableQuery() {
    this(null, List.of(), List.of(), null, null, null, true, CellFormat.JSON, null, null);
  }

  private AirtableQuery(
      String formula,
      List<Sort> sort,
      List<String> fields,
      Integer maxRecords,
      Integer pageSize,
      String view,
      boolean returnFieldsByFieldId,
      CellFormat cellFormat,
      String timeZone,
      String userLocale) {
    this.formula = formula;
    this.sort = List.copyOf(sort);
    this.fields = List.copyOf(fields);
    this.maxRecords = maxRecords;
    this.pageSize = pageSize;
    this.view = view;
    this.returnFieldsByFieldId = returnFieldsByFieldId;
    this.cellFormat = cellFormat;
    this.timeZone = timeZone;
    this.userLocale = userLocale;
  }

  // ---- getters ----

  public String getFormula() {
    return formula;
  }

  public List<Sort> getSort() {
    return sort;
  }

  public List<String> getFields() {
    return fields;
  }

  public Integer getMaxRecords() {
    return maxRecords;
  }

  public Integer getPageSize() {
    return pageSize;
  }

  public String getView() {
    return view;
  }

  public boolean isReturnFieldsByFieldId() {
    return returnFieldsByFieldId;
  }

  public CellFormat getCellFormat() {
    return cellFormat;
  }

  public String getTimeZone() {
    return timeZone;
  }

  public String getUserLocale() {
    return userLocale;
  }

  // ---- withers ----

  public AirtableQuery withFormula(String formula) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  /** Append a sort clause (ascending). */
  public AirtableQuery withSort(String field) {
    return withSort(field, SortDirection.ASC);
  }

  /** Append a sort clause. */
  public AirtableQuery withSort(String field, SortDirection direction) {
    List<Sort> next = new ArrayList<>(sort);
    next.add(new Sort(field, direction));
    return new AirtableQuery(
        formula,
        next,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  /** Restrict the response to the given field IDs/names. */
  public AirtableQuery withFields(List<String> fields) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  public AirtableQuery withMaxRecords(Integer maxRecords) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  public AirtableQuery withPageSize(Integer pageSize) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  /** Scope the query to a view by raw view ID or name. */
  public AirtableQuery withView(String view) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  /**
   * Scope the query to a generated view constant: {@code new
   * AirtableQuery().withView(ContactsView.ACTIVE)} instead of reaching for {@code .getId()}.
   */
  public AirtableQuery withView(AirtableView view) {
    return withView(view.getId());
  }

  public AirtableQuery withReturnFieldsByFieldId(boolean returnFieldsByFieldId) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  public AirtableQuery withCellFormat(CellFormat cellFormat) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  public AirtableQuery withTimeZone(String timeZone) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  public AirtableQuery withUserLocale(String userLocale) {
    return new AirtableQuery(
        formula,
        sort,
        fields,
        maxRecords,
        pageSize,
        view,
        returnFieldsByFieldId,
        cellFormat,
        timeZone,
        userLocale);
  }

  /**
   * Convert to query parameters using Airtable's list-records shape: {@code filterByFormula},
   * {@code fields[]}, {@code sort[i][field]}, {@code sort[i][direction]}, {@code maxRecords},
   * {@code pageSize}, {@code view}, {@code returnFieldsByFieldId}, {@code cellFormat}, {@code
   * timeZone}, {@code userLocale}.
   */
  public List<Param> toParameters() {
    List<Param> params = new ArrayList<>();
    if (formula != null && !formula.isEmpty()) {
      params.add(new Param("filterByFormula", formula));
    }
    for (String field : fields) {
      params.add(new Param("fields[]", field));
    }
    for (int i = 0; i < sort.size(); i++) {
      params.add(new Param("sort[" + i + "][field]", sort.get(i).field()));
      params.add(new Param("sort[" + i + "][direction]", sort.get(i).direction().wire()));
    }
    if (maxRecords != null) {
      params.add(new Param("maxRecords", maxRecords.toString()));
    }
    if (pageSize != null) {
      params.add(new Param("pageSize", pageSize.toString()));
    }
    if (view != null && !view.isEmpty()) {
      params.add(new Param("view", view));
    }
    if (returnFieldsByFieldId) {
      params.add(new Param("returnFieldsByFieldId", "true"));
    }
    if (cellFormat != CellFormat.JSON) {
      params.add(new Param("cellFormat", cellFormat.wire()));
    }
    if (timeZone != null && !timeZone.isEmpty()) {
      params.add(new Param("timeZone", timeZone));
    }
    if (userLocale != null && !userLocale.isEmpty()) {
      params.add(new Param("userLocale", userLocale));
    }
    return params;
  }
}
