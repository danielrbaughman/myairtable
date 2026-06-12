// myairtable-acvg — bounded multi-ID get on DictTable.
//
// The 4-in-flight window itself is timing behavior and hard to unit test;
// what this pins is the observable contract that must survive the windowed
// submission: each ID's payload comes back in the slot it was requested in.

import Foundation
import Testing

@testable import MyAirtableStatic

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// URLProtocol stub that echoes the record ID from the request URL path back
/// as a single-record payload. Stateless (the response is derived entirely
/// from the request), so concurrent in-flight requests are safe.
private final class EchoRecordURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        let recordId = url.lastPathComponent
        let body = Data(#"{"id": "\#(recordId)", "fields": {"fldName": "name-\#(recordId)"}}"#.utf8)
        let response = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@Suite("DictTable bounded multi-get")
struct TestDictTableMultiGet {
    private func makeTable() -> DictTable {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [EchoRecordURLProtocol.self]
        let client = AirtableClient(
            baseId: "appX",
            apiKey: "key",
            session: URLSession(configuration: config)
        )
        return DictTable(tableId: "tblStub", client: client)
    }

    @Test func preservesCallerOrder() async throws {
        // Deliberately non-sorted so positional mix-ups can't pass by luck;
        // larger than the 4-wide window so refill submission is exercised.
        let ids = [
            "rec07", "rec01", "rec12", "rec03", "rec09", "rec05", "rec11", "rec02", "rec08", "rec04", "rec10", "rec06",
        ]
        let records = try await makeTable().get(ids)
        #expect(records.map(\.id) == ids)
    }

    @Test func emptyInputReturnsEmpty() async throws {
        let records = try await makeTable().get([String]())
        #expect(records.isEmpty)
    }
}
