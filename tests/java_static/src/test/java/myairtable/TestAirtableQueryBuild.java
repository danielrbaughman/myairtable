package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * J-port of Kotlin K2.4 — AirtableQuery → list-records parameter encoding for every option. Parity:
 * Kotlin/Swift TestAirtableQueryBuild.
 */
class TestAirtableQueryBuild {

  private static Map<String, List<String>> params(AirtableQuery query) {
    Map<String, List<String>> grouped = new LinkedHashMap<>();
    for (AirtableQuery.Param p : query.toParameters()) {
      grouped.computeIfAbsent(p.name(), k -> new ArrayList<>()).add(p.value());
    }
    return grouped;
  }

  @Test
  void defaultQueryOnlyEmitsReturnFieldsByFieldId() {
    assertEquals(
        List.of(new AirtableQuery.Param("returnFieldsByFieldId", "true")),
        new AirtableQuery().toParameters());
  }

  @Test
  void formulaEncodesAsFilterByFormula() {
    Map<String, List<String>> p = params(new AirtableQuery().withFormula("NOT({Name}=BLANK())"));
    assertEquals(List.of("NOT({Name}=BLANK())"), p.get("filterByFormula"));
  }

  @Test
  void emptyFormulaIsOmitted() {
    assertFalse(params(new AirtableQuery().withFormula("")).containsKey("filterByFormula"));
  }

  @Test
  void fieldsEncodeAsRepeatedArrayParams() {
    Map<String, List<String>> p = params(new AirtableQuery().withFields(List.of("fldA", "fldB")));
    assertEquals(List.of("fldA", "fldB"), p.get("fields[]"));
  }

  @Test
  void sortEncodesIndexedFieldAndDirection() {
    AirtableQuery q = new AirtableQuery().withSort("Name").withSort("Age", SortDirection.DESC);
    Map<String, List<String>> p = params(q);
    assertEquals(List.of("Name"), p.get("sort[0][field]"));
    assertEquals(List.of("asc"), p.get("sort[0][direction]"));
    assertEquals(List.of("Age"), p.get("sort[1][field]"));
    assertEquals(List.of("desc"), p.get("sort[1][direction]"));
  }

  @Test
  void maxRecordsAndPageSizeEncode() {
    Map<String, List<String>> p = params(new AirtableQuery().withMaxRecords(10).withPageSize(5));
    assertEquals(List.of("10"), p.get("maxRecords"));
    assertEquals(List.of("5"), p.get("pageSize"));
  }

  @Test
  void viewEncodesAndEmptyViewIsOmitted() {
    assertEquals(
        List.of("Grid view"), params(new AirtableQuery().withView("Grid view")).get("view"));
    assertFalse(params(new AirtableQuery().withView("")).containsKey("view"));
  }

  @Test
  void returnFieldsByFieldIdCanBeDisabled() {
    assertFalse(
        params(new AirtableQuery().withReturnFieldsByFieldId(false))
            .containsKey("returnFieldsByFieldId"));
  }

  @Test
  void cellFormatOnlyEmittedWhenNotJson() {
    assertFalse(params(new AirtableQuery()).containsKey("cellFormat"));
    assertEquals(
        List.of("string"),
        params(new AirtableQuery().withCellFormat(AirtableQuery.CellFormat.STRING))
            .get("cellFormat"));
  }

  @Test
  void timeZoneAndUserLocaleEncode() {
    Map<String, List<String>> p =
        params(new AirtableQuery().withTimeZone("America/Chicago").withUserLocale("en-us"));
    assertEquals(List.of("America/Chicago"), p.get("timeZone"));
    assertEquals(List.of("en-us"), p.get("userLocale"));
  }

  @Test
  void combinedQueryEmitsExpectedParameterCount() {
    AirtableQuery q =
        new AirtableQuery()
            .withFormula("X")
            .withFields(List.of("fldA", "fldB"))
            .withMaxRecords(10)
            .withPageSize(5)
            .withView("Grid")
            .withTimeZone("America/Chicago")
            .withUserLocale("en-us")
            .withSort("Name");
    // formula + 2 fields + 2 sort items + maxRecords + pageSize + view +
    // returnFieldsByFieldId + timeZone + userLocale = 11
    assertEquals(11, q.toParameters().size());
  }

  @Test
  void copySemanticsProduceIndependentQueries() {
    // The Java analog of Kotlin's data-class copy() is the immutable wither chain.
    AirtableQuery base = new AirtableQuery().withFormula("X");
    AirtableQuery modified = base.withMaxRecords(1);
    assertNull(params(base).get("maxRecords"));
    assertEquals(List.of("1"), params(modified).get("maxRecords"));
    assertEquals(List.of("X"), params(modified).get("filterByFormula"));
  }
}
