// F2.8 — Verify AirtableQuery serializes to the URL query items Airtable
// expects. Each test covers one field of the builder; one final test checks
// the combined shape.

import Foundation
import Testing

@testable import MyAirtableStatic

@Suite("AirtableQuery.toQueryItems")
struct TestAirtableQueryBuild {
    @Test("Empty query still emits returnFieldsByFieldId=true (default)")
    func testEmpty() {
        let q = AirtableQuery()
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "returnFieldsByFieldId", value: "true")))
        #expect(items.count == 1)
    }

    @Test("formula is serialized as filterByFormula")
    func testFormula() {
        let q = AirtableQuery(formula: "NOT({Name}=BLANK())")
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "filterByFormula", value: "NOT({Name}=BLANK())")))
    }

    @Test("empty-string formula is omitted")
    func testEmptyFormula() {
        let q = AirtableQuery(formula: "")
        let items = q.toQueryItems()
        #expect(!items.contains { $0.name == "filterByFormula" })
    }

    @Test("fields serialize as repeated fields[] items in order")
    func testFields() {
        let q = AirtableQuery(fields: ["fldA", "fldB", "fldC"])
        let items = q.toQueryItems().filter { $0.name == "fields[]" }
        #expect(
            items == [
                URLQueryItem(name: "fields[]", value: "fldA"),
                URLQueryItem(name: "fields[]", value: "fldB"),
                URLQueryItem(name: "fields[]", value: "fldC"),
            ])
    }

    @Test("single sort clause serializes as sort[0][field]/sort[0][direction]")
    func testSortSingle() {
        let q = AirtableQuery(sort: [Sort(field: "Name", direction: .desc)])
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "sort[0][field]", value: "Name")))
        #expect(items.contains(URLQueryItem(name: "sort[0][direction]", value: "desc")))
    }

    @Test("multiple sort clauses are indexed in order")
    func testSortMultiple() {
        let q = AirtableQuery(sort: [
            Sort(field: "A", direction: .asc),
            Sort(field: "B", direction: .desc),
        ])
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "sort[0][field]", value: "A")))
        #expect(items.contains(URLQueryItem(name: "sort[0][direction]", value: "asc")))
        #expect(items.contains(URLQueryItem(name: "sort[1][field]", value: "B")))
        #expect(items.contains(URLQueryItem(name: "sort[1][direction]", value: "desc")))
    }

    @Test("maxRecords and pageSize serialize as integer strings")
    func testMaxRecordsAndPageSize() {
        let q = AirtableQuery(maxRecords: 100, pageSize: 25)
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "maxRecords", value: "100")))
        #expect(items.contains(URLQueryItem(name: "pageSize", value: "25")))
    }

    @Test("view name is passed through")
    func testView() {
        let q = AirtableQuery(view: "Grid view")
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "view", value: "Grid view")))
    }

    @Test("returnFieldsByFieldId=false omits the item")
    func testReturnFieldsByFieldIdOff() {
        let q = AirtableQuery(returnFieldsByFieldId: false)
        let items = q.toQueryItems()
        #expect(!items.contains { $0.name == "returnFieldsByFieldId" })
    }

    @Test("cellFormat .string is serialized; .json (default) is omitted")
    func testCellFormat() {
        let jsonQ = AirtableQuery(cellFormat: .json)
        #expect(!jsonQ.toQueryItems().contains { $0.name == "cellFormat" })

        let strQ = AirtableQuery(cellFormat: .string)
        #expect(strQ.toQueryItems().contains(URLQueryItem(name: "cellFormat", value: "string")))
    }

    @Test("timeZone and userLocale are passed through when non-empty")
    func testTimeZoneAndLocale() {
        let q = AirtableQuery(timeZone: "America/New_York", userLocale: "en-US")
        let items = q.toQueryItems()
        #expect(items.contains(URLQueryItem(name: "timeZone", value: "America/New_York")))
        #expect(items.contains(URLQueryItem(name: "userLocale", value: "en-US")))
    }

    @Test("Fluent builders produce the same output as direct init")
    func testFluentBuildersEquivalence() {
        let direct = AirtableQuery(
            formula: "NOT({Name}=BLANK())",
            sort: [Sort(field: "Name", direction: .asc)],
            fields: ["fldA"],
            maxRecords: 10
        )
        let fluent = AirtableQuery()
            .formula("NOT({Name}=BLANK())")
            .sort(field: "Name", direction: .asc)
            .fields(["fldA"])
            .maxRecords(10)
        #expect(direct == fluent)
    }

    @Test("Combined query emits expected parameter count")
    func testCombinedShape() {
        let q = AirtableQuery(
            formula: "{X}=1",
            sort: [Sort(field: "A", direction: .asc)],
            fields: ["fld1", "fld2"],
            maxRecords: 50,
            pageSize: 10,
            view: "v"
        )
        let items = q.toQueryItems()
        // 1 filterByFormula + 2 fields[] + 2 sort + 1 maxRecords + 1 pageSize
        // + 1 view + 1 returnFieldsByFieldId = 9
        #expect(items.count == 9)
    }
}

// MARK: - URL encoding

@Suite("Client URL encoding")
struct TestClientUrlEncoding {
    @Test("Plus signs in formulas are percent-encoded (Airtable decodes raw + as space)")
    func plusSignEncoded() async throws {
        let client = AirtableClient(baseId: "appTEST", apiKey: "key")
        let url = try await client.tableURL(
            "tblTEST",
            query: [URLQueryItem(name: "filterByFormula", value: "FIND(\"x\",{f})=LEN({f})+1")]
        )
        let query = url.query(percentEncoded: true) ?? ""
        #expect(!query.contains("+"), "raw + must not survive encoding: \(query)")
        #expect(query.contains("%2B"), "expected %2B in: \(query)")
    }
}

// myairtable-p7eb — multi-page payloads (live offset token) must not be cached.
@Suite("List-cache offset probe")
struct TestContinuationOffsetProbe {
    @Test func payloadWithOffsetIsDetected() {
        let data = Data(#"{"records": [], "offset": "itrAbc/recDef"}"#.utf8)
        #expect(AirtableClient.hasContinuationOffset(data))
    }

    @Test func completePayloadIsNotFlagged() {
        #expect(!AirtableClient.hasContinuationOffset(Data(#"{"records": []}"#.utf8)))
        #expect(!AirtableClient.hasContinuationOffset(Data(#"{"records": [], "offset": ""}"#.utf8)))
        #expect(!AirtableClient.hasContinuationOffset(Data("not json".utf8)))
    }
}
