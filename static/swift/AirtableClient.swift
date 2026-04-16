import Foundation

#if canImport(FoundationNetworking)
    import FoundationNetworking
#endif

/// Actor wrapping `URLSession` for Airtable REST API calls. All network I/O
/// flows through this actor; `OrmTable` / `DictTable` structs are `Sendable`
/// struct front-ends that forward here.
///
/// The client owns a `CacheStore` actor (populated in F9) keyed by
/// `(tableId, cacheKey)`. On mutation, cache invalidation happens via
/// `cache.invalidate(.table(tableId))`.
///
/// Airtable REST reference: https://airtable.com/developers/web/api/
public actor AirtableClient {
    // MARK: - Configuration

    public let baseId: String
    public let apiKey: String
    public let apiBase: URL
    public let cache: CacheStore

    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    /// Max retries for transient HTTP failures (429, 5xx). Total wait is
    /// roughly `baseRetryDelay * 2^attempt` up to `maxRetries`.
    public let maxRetries: Int
    public let baseRetryDelay: TimeInterval

    // MARK: - Init

    public init(
        baseId: String,
        apiKey: String,
        apiBase: URL = URL(string: "https://api.airtable.com/v0")!,
        session: URLSession = .shared,
        cache: CacheStore = CacheStore(),
        maxRetries: Int = 3,
        baseRetryDelay: TimeInterval = 0.5
    ) {
        self.baseId = baseId
        self.apiKey = apiKey
        self.apiBase = apiBase
        self.session = session
        self.cache = cache
        self.maxRetries = maxRetries
        self.baseRetryDelay = baseRetryDelay

        let enc = JSONEncoder()
        enc.dateEncodingStrategy = .iso8601
        self.encoder = enc

        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        self.decoder = dec
    }

    // MARK: - Endpoint builders

    /// `/<baseId>/<tableId>` for list / create.
    func tableURL(_ tableId: String, query: [URLQueryItem] = []) throws -> URL {
        guard
            var components = URLComponents(
                url: apiBase.appendingPathComponent(baseId).appendingPathComponent(tableId),
                resolvingAgainstBaseURL: false
            )
        else {
            throw AirtableError.invalidUrl
        }
        if !query.isEmpty {
            components.queryItems = query
        }
        guard let url = components.url else { throw AirtableError.invalidUrl }
        return url
    }

    /// `/<baseId>/<tableId>/<recordId>` for single record ops.
    func recordURL(_ tableId: String, recordId: String) throws -> URL {
        return try tableURL(tableId).appendingPathComponent(recordId)
    }

    // MARK: - Request execution

    /// Send a request with automatic retry on 429/5xx.
    func send(_ request: URLRequest) async throws -> Data {
        var attempt = 0
        while true {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw AirtableError.http(statusCode: 0, body: nil)
            }
            if (200..<300).contains(http.statusCode) {
                return data
            }

            let isRetryable = http.statusCode == 429 || (500..<600).contains(http.statusCode)
            if isRetryable && attempt < maxRetries {
                let retryAfter = retryAfterSeconds(from: http) ?? baseRetryDelay * pow(2.0, Double(attempt))
                try await Task.sleep(nanoseconds: UInt64(retryAfter * 1_000_000_000))
                attempt += 1
                continue
            }

            if http.statusCode == 429 {
                throw AirtableError.rateLimited(retryAfter: retryAfterSeconds(from: http))
            }

            // Try to decode a structured error envelope.
            if let envelope = try? decoder.decode(AirtableErrorEnvelope.self, from: data) {
                throw envelope.toAirtableError()
            }
            let body = String(data: data, encoding: .utf8)
            throw AirtableError.http(statusCode: http.statusCode, body: body)
        }
    }

    private func retryAfterSeconds(from response: HTTPURLResponse) -> TimeInterval? {
        guard let raw = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
        return Double(raw)
    }

    /// Decorate a request with Authorization + Content-Type headers.
    func authorized(_ url: URL, method: String = "GET", body: Data? = nil) -> URLRequest {
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        if body != nil {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = body
        }
        return req
    }

    // MARK: - Record endpoints (Data-level)
    //
    // These return raw JSON bytes so typed and dict table wrappers can
    // re-decode into their preferred shape (model vs Fields). Cache reads
    // happen at this layer (keyed on table + query/record).

    /// GET list records. Returns raw response bytes (envelope:
    /// `{records: [...], offset: "..."}`).
    public func listRecords(tableId: String, query: AirtableQuery) async throws -> Data {
        let url = try tableURL(tableId, query: query.toQueryItems())
        let req = authorized(url)
        return try await send(req)
    }

    /// GET a single record. Returns raw response bytes (envelope:
    /// `{id, createdTime, fields}`). Always sets `returnFieldsByFieldId=true`
    /// so the response keys match the generator's field-ID constants.
    public func getRecord(tableId: String, recordId: String) async throws -> Data {
        let base = try recordURL(tableId, recordId: recordId)
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw AirtableError.invalidUrl
        }
        components.queryItems = [URLQueryItem(name: "returnFieldsByFieldId", value: "true")]
        guard let url = components.url else { throw AirtableError.invalidUrl }
        let req = authorized(url)
        return try await send(req)
    }

    /// POST to create records. `body` is a JSON-encoded
    /// `{records: [{fields: {...}}, ...]}` envelope. Cache is invalidated
    /// for the table on success.
    public func createRecords(tableId: String, body: Data) async throws -> Data {
        let url = try tableURL(tableId)
        let req = authorized(url, method: "POST", body: body)
        let response = try await send(req)
        await cache.invalidate(.table(tableId))
        return response
    }

    /// PATCH to update records. `body` is `{records: [{id, fields}, ...]}`.
    /// Cache is invalidated for the table on success.
    public func updateRecords(tableId: String, body: Data) async throws -> Data {
        let url = try tableURL(tableId)
        let req = authorized(url, method: "PATCH", body: body)
        let response = try await send(req)
        await cache.invalidate(.table(tableId))
        return response
    }

    /// DELETE a single record. Cache is invalidated for the table on success.
    public func deleteRecord(tableId: String, recordId: String) async throws -> Data {
        let url = try recordURL(tableId, recordId: recordId)
        let req = authorized(url, method: "DELETE")
        let response = try await send(req)
        await cache.invalidate(.table(tableId))
        return response
    }

    /// DELETE multiple records (via `records[]` query params).
    public func deleteRecords(tableId: String, recordIds: [String]) async throws -> Data {
        let items = recordIds.map { URLQueryItem(name: "records[]", value: $0) }
        let url = try tableURL(tableId, query: items)
        let req = authorized(url, method: "DELETE")
        let response = try await send(req)
        await cache.invalidate(.table(tableId))
        return response
    }
}
