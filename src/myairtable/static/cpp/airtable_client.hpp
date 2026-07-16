#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
#include <optional>
#include <random>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "airtable_exception.hpp"
#include "airtable_json.hpp"
#include "airtable_query.hpp"
#include "cache_store.hpp"
#include "curl_transport.hpp"

namespace myairtable {

/// Percent-encode for a URL path segment or query value: RFC 3986 unreserved
/// characters pass through, EVERYTHING else (including '+', which Airtable
/// would otherwise decode as a space inside filterByFormula) becomes %XX.
/// Matches .NET Uri.EscapeDataString / the C# client, verified live there.
inline std::string url_encode(const std::string& text) {
    static constexpr char hex[] = "0123456789ABCDEF";
    std::string out;
    out.reserve(text.size() * 3);
    for (const unsigned char c : text) {
        const bool unreserved = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                                (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' ||
                                c == '~';
        if (unreserved) {
            out.push_back(static_cast<char>(c));
        } else {
            out.push_back('%');
            out.push_back(hex[c >> 4]);
            out.push_back(hex[c & 0x0F]);
        }
    }
    return out;
}

/// The blocking Airtable REST client. Thread-safe: per-request curl handles
/// over a shared DNS/TLS-session cache; retry-with-jitter on 429/5xx.
///
/// Endpoints return the raw response payload (a JSON string) — the typed
/// table/model layers decode. The cache (F2.10) wraps list/get reads.
class AirtableClient {
  public:
    static constexpr const char* kApiRoot = "https://api.airtable.com/v0";
    static constexpr int kMaxRetries = 4;
    static constexpr double kBaseRetryDelaySeconds = 0.5;
    static constexpr double kRetryJitterCapSeconds = 1.0;
    static constexpr double kMaxRetryDelaySeconds = 30.0;

    explicit AirtableClient(std::string base_id, std::string api_key, double cache_seconds = 0.0)
        : AirtableClient(std::move(base_id), std::move(api_key), &curl_perform,
                         kBaseRetryDelaySeconds, kRetryJitterCapSeconds, cache_seconds) {}

    /// Injectable-transport constructor: production uses the curl transport;
    /// tests inject a FakeTransport (and usually zero delays).
    AirtableClient(std::string base_id, std::string api_key, Transport transport,
                   double base_retry_delay = kBaseRetryDelaySeconds,
                   double jitter_cap = kRetryJitterCapSeconds, double cache_seconds = 0.0)
        : base_id_(std::move(base_id)), api_key_(std::move(api_key)),
          transport_(std::move(transport)), base_retry_delay_(base_retry_delay),
          jitter_cap_(jitter_cap), cache_(cache_seconds) {
        if (base_id_.empty()) {
            throw MissingCredentialsError("base id is empty");
        }
        if (api_key_.empty()) {
            throw MissingCredentialsError("api key is empty");
        }
    }

    const std::string& base_id() const { return base_id_; }
    CacheStore& cache() { return cache_; }
    void invalidate_cache(const std::string& table_id) { cache_.invalidate(table_id); }
    void invalidate_all_caches() { cache_.invalidate_all(); }

    // ---- record endpoints ------------------------------------------------------

    /// GET one page of records for `query` (cached by query). A payload with a
    /// live `offset` continuation token is returned but never stored — the
    /// token expires server-side and a cache hit would replay a dead token.
    std::string list_records(const std::string& table_id, const AirtableQuery& query) {
        const std::string url = table_url(table_id, query.to_parameters());
        return cache_.get_or_add(
            table_id, "list:" + cache_key_for_query(query),
            [&] { return send("GET", url, std::nullopt, /*idempotent=*/true); },
            [](const std::string& payload) { return !has_continuation_offset(payload); });
    }

    /// GET a single record by id (cached).
    std::string get_record(const std::string& table_id, const std::string& record_id) {
        // returnFieldsByFieldId so the response keys match the generated field-id
        // constants (live-caught in the C# effort: without it, fields key by NAME).
        const std::string url = std::string(kApiRoot) + "/" + url_encode(base_id_) + "/" +
                                url_encode(table_id) + "/" + url_encode(record_id) +
                                "?returnFieldsByFieldId=true";
        return cache_.get_or_add(table_id, "rec:" + record_id, [&] {
            return send("GET", url, std::nullopt, /*idempotent=*/true);
        });
    }

    /// POST new records. NOT idempotent — a retried 5xx could double-insert.
    std::string create_records(const std::string& table_id, const std::string& body) {
        const std::string url =
            std::string(kApiRoot) + "/" + url_encode(base_id_) + "/" + url_encode(table_id);
        std::string result = send("POST", url, body, /*idempotent=*/false);
        cache_.invalidate(table_id);
        return result;
    }

    /// PATCH the records collection (update-by-id and upsert). Update-by-id and
    /// merge-keyed upsert are idempotent; an empty-merge upsert inserts and is
    /// NOT — callers pass `idempotent` accordingly.
    std::string update_records(const std::string& table_id, const std::string& body,
                               bool idempotent = true) {
        const std::string url =
            std::string(kApiRoot) + "/" + url_encode(base_id_) + "/" + url_encode(table_id);
        std::string result = send("PATCH", url, body, idempotent);
        cache_.invalidate(table_id);
        return result;
    }

    std::string delete_record(const std::string& table_id, const std::string& record_id) {
        const std::string url = std::string(kApiRoot) + "/" + url_encode(base_id_) + "/" +
                                url_encode(table_id) + "/" + url_encode(record_id);
        std::string result = send("DELETE", url, std::nullopt, /*idempotent=*/true);
        cache_.invalidate(table_id);
        return result;
    }

    std::string delete_records(const std::string& table_id,
                               const std::vector<std::string>& record_ids) {
        std::vector<std::pair<std::string, std::string>> params;
        params.reserve(record_ids.size());
        for (const auto& id : record_ids) {
            params.emplace_back("records[]", id);
        }
        std::string result =
            send("DELETE", table_url(table_id, params), std::nullopt, /*idempotent=*/true);
        cache_.invalidate(table_id);
        return result;
    }

    /// A stable cache key: both halves encoded (a formula containing `=`/`&`
    /// can't collide with a structurally different query) and sorted (parameter
    /// order never splits the key). Java/Kotlin/C# parity.
    static std::string cache_key_for_query(const AirtableQuery& query) {
        std::vector<std::string> encoded;
        for (const auto& [key, value] : query.to_parameters()) {
            encoded.push_back(url_encode(key) + "=" + url_encode(value));
        }
        std::sort(encoded.begin(), encoded.end());
        std::string out;
        for (const auto& part : encoded) {
            if (!out.empty()) {
                out.push_back('&');
            }
            out += part;
        }
        return out;
    }

    /// Does a list payload carry a live continuation offset?
    static bool has_continuation_offset(const std::string& payload) {
        const json parsed = json::parse(payload, /*cb=*/nullptr, /*allow_exceptions=*/false);
        return !parsed.is_discarded() && parsed.is_object() && parsed.contains("offset") &&
               parsed.at("offset").is_string() && !parsed.at("offset").get<std::string>().empty();
    }

    // ---- URL building --------------------------------------------------------------

    /// Records URL for a table with an encoded query string. Param names (e.g.
    /// fields[]) keep raw brackets — Airtable accepts them; only VALUES are
    /// percent-encoded (the '+' encoding is the live-verified hazard).
    std::string table_url(const std::string& table_id,
                          const std::vector<std::pair<std::string, std::string>>& params) const {
        std::string url =
            std::string(kApiRoot) + "/" + url_encode(base_id_) + "/" + url_encode(table_id);
        if (params.empty()) {
            return url;
        }
        url.push_back('?');
        bool first = true;
        for (const auto& [key, value] : params) {
            if (!first) {
                url.push_back('&');
            }
            url += key + "=" + url_encode(value);
            first = false;
        }
        return url;
    }

    // ---- transport -------------------------------------------------------------------

    /// Send with bearer auth and retry-with-jitter. A 429 is always retried
    /// (nothing was applied); 5xx and transport failures are retried ONLY when
    /// `idempotent` — a non-idempotent retry could double-apply.
    std::string send(const std::string& method, const std::string& url,
                     const std::optional<std::string>& body, bool idempotent) {
        int attempt = 0;
        while (true) {
            HttpResponse response;
            try {
                HttpRequest request{method, url, body};
                request.headers.emplace_back("Authorization", "Bearer " + api_key_);
                if (body.has_value()) {
                    request.headers.emplace_back("Content-Type", "application/json");
                }
                response = transport_(request);
            } catch (const TransportFailure& failure) {
                if (idempotent && attempt < kMaxRetries) {
                    delay(std::nullopt, attempt++);
                    continue;
                }
                throw NetworkError(failure.message);
            }

            if (response.status >= 200 && response.status <= 299) {
                return response.body;
            }

            if (response.status == 429) {
                const auto retry_after = parse_retry_after(response);
                if (attempt < kMaxRetries) {
                    delay(retry_after, attempt++);
                    continue;
                }
                throw RateLimitedError(retry_after);
            }

            if (response.status >= 500 && idempotent && attempt < kMaxRetries) {
                delay(std::nullopt, attempt++);
                continue;
            }

            throw_terminal(response);
        }
    }

    /// Total backoff in seconds. An explicit Retry-After wins; otherwise
    /// exponential base * 2^attempt. Decorrelation jitter of
    /// rand * min(delay, jitter_cap) is added; the final value is capped at
    /// max_delay — including a broken `Retry-After: 999999`. Pure.
    static double compute_retry_delay_seconds(std::optional<double> retry_after_seconds,
                                              double base_retry_delay, int attempt,
                                              double jitter_cap, double max_delay, double rand) {
        const double delay = retry_after_seconds.has_value()
                                 ? std::max(0.0, *retry_after_seconds)
                                 : base_retry_delay * std::pow(2.0, attempt);
        const double jitter = rand * std::min(delay, jitter_cap);
        return std::min(delay + jitter, max_delay);
    }

    /// Retry-After per RFC 9110: delta-seconds or an HTTP-date.
    static std::optional<double> parse_retry_after(const HttpResponse& response) {
        const auto it = response.headers.find("retry-after");
        if (it == response.headers.end()) {
            return std::nullopt;
        }
        try {
            size_t consumed = 0;
            const double delta = std::stod(it->second, &consumed);
            if (consumed == it->second.size()) {
                return std::max(0.0, delta);
            }
        } catch (const std::exception&) {
            // fall through to the HTTP-date form
        }
        return seconds_until_http_date(it->second, std::time(nullptr));
    }

  private:
    [[noreturn]] void throw_terminal(const HttpResponse& response) const {
        // Prefer the structured envelope; fall back to a bare HttpError.
        const json parsed = json::parse(response.body, /*cb=*/nullptr, /*allow_exceptions=*/false);
        if (!parsed.is_discarded() && parsed.is_object() && parsed.contains("error")) {
            throw decode_error_envelope(response.body);
        }
        throw HttpError(response.status, response.body);
    }

    void delay(std::optional<double> retry_after_seconds, int attempt) const {
        static thread_local std::mt19937 rng{std::random_device{}()};
        std::uniform_real_distribution<double> dist(0.0, 1.0);
        const double seconds =
            compute_retry_delay_seconds(retry_after_seconds, base_retry_delay_, attempt,
                                        jitter_cap_, kMaxRetryDelaySeconds, dist(rng));
        if (seconds > 0.0) {
            std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
        }
    }

    std::string base_id_;
    std::string api_key_;
    Transport transport_;
    double base_retry_delay_;
    double jitter_cap_;
    CacheStore cache_;
};

} // namespace myairtable
