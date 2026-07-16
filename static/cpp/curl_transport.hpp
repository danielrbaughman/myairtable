#pragma once

#include <curl/curl.h>

#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace myairtable {

/// A transport-level request (method + absolute URL + optional JSON body).
struct HttpRequest {
    std::string method;
    std::string url;
    std::optional<std::string> body{};
    std::vector<std::pair<std::string, std::string>> headers{};
};

/// A transport-level response. Header names are lower-cased.
struct HttpResponse {
    int status = 0;
    std::string body;
    std::map<std::string, std::string> headers;
};

/// Thrown by a transport on connection-level failure (DNS, reset, timeout).
/// Internal signal only — the client converts it to NetworkError or retries.
struct TransportFailure {
    std::string message;
};

/// The injectable transport seam: production uses curl_transport(); tests
/// inject a FakeTransport. Throws TransportFailure on connection-level errors.
using Transport = std::function<HttpResponse(const HttpRequest&)>;

namespace detail {

inline size_t curl_write_body(char* data, size_t size, size_t nmemb, void* out) {
    static_cast<std::string*>(out)->append(data, size * nmemb);
    return size * nmemb;
}

inline size_t curl_write_header(char* data, size_t size, size_t nmemb, void* out) {
    const std::string line(data, size * nmemb);
    const auto colon = line.find(':');
    if (colon != std::string::npos) {
        std::string key = line.substr(0, colon);
        for (auto& c : key) {
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        }
        std::string value = line.substr(colon + 1);
        const auto begin = value.find_first_not_of(" \t");
        const auto end = value.find_last_not_of(" \t\r\n");
        if (begin != std::string::npos) {
            static_cast<std::map<std::string, std::string>*>(out)->emplace(
                key, value.substr(begin, end - begin + 1));
        }
    }
    return size * nmemb;
}

/// Process-lifetime share of DNS + TLS session caches. Per-request easy handles
/// keep the client trivially thread-safe (easy handles are not), but without a
/// CURLSH every call would pay fresh DNS + a full TLS handshake.
class CurlShare {
  public:
    CurlShare() : share_(curl_share_init()) {
        curl_share_setopt(share_, CURLSHOPT_SHARE, CURL_LOCK_DATA_DNS);
        curl_share_setopt(share_, CURLSHOPT_SHARE, CURL_LOCK_DATA_SSL_SESSION);
        curl_share_setopt(share_, CURLSHOPT_LOCKFUNC, &CurlShare::lock);
        curl_share_setopt(share_, CURLSHOPT_UNLOCKFUNC, &CurlShare::unlock);
        curl_share_setopt(share_, CURLSHOPT_USERDATA, this);
    }
    ~CurlShare() { curl_share_cleanup(share_); }
    CurlShare(const CurlShare&) = delete;
    CurlShare& operator=(const CurlShare&) = delete;

    CURLSH* handle() const { return share_; }

  private:
    static void lock(CURL*, curl_lock_data data, curl_lock_access, void* self) {
        static_cast<CurlShare*>(self)->mutexes_[lock_index(data)].lock();
    }
    static void unlock(CURL*, curl_lock_data data, void* self) {
        static_cast<CurlShare*>(self)->mutexes_[lock_index(data)].unlock();
    }
    static size_t lock_index(curl_lock_data data) {
        return static_cast<size_t>(data) % CURL_LOCK_DATA_LAST;
    }

    CURLSH* share_;
    std::mutex mutexes_[CURL_LOCK_DATA_LAST];
};

inline CurlShare& shared_curl_state() {
    // curl_global_init must run exactly once before any easy handle exists;
    // a function-local static gives call_once semantics AND process lifetime.
    static std::once_flag init_flag;
    std::call_once(init_flag, [] { curl_global_init(CURL_GLOBAL_DEFAULT); });
    static CurlShare share;
    return share;
}

} // namespace detail

/// The production transport: one easy handle per request (thread safety),
/// attached to the process-wide share for DNS/TLS-session reuse.
inline HttpResponse curl_perform(const HttpRequest& request) {
    auto& share = detail::shared_curl_state();

    const std::unique_ptr<CURL, void (*)(CURL*)> handle(curl_easy_init(), &curl_easy_cleanup);
    if (!handle) {
        throw TransportFailure{"curl_easy_init failed"};
    }
    CURL* curl = handle.get();

    HttpResponse response;
    char error_buffer[CURL_ERROR_SIZE] = {0};

    curl_easy_setopt(curl, CURLOPT_URL, request.url.c_str());
    curl_easy_setopt(curl, CURLOPT_SHARE, share.handle());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, &detail::curl_write_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response.body);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, &detail::curl_write_header);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, &response.headers);
    curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, error_buffer);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 15L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, ""); // enable compression

    if (request.method != "GET") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, request.method.c_str());
    }
    if (request.body.has_value()) {
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request.body->c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(request.body->size()));
    }

    curl_slist* header_list = nullptr;
    for (const auto& [key, value] : request.headers) {
        header_list = curl_slist_append(header_list, (key + ": " + value).c_str());
    }
    const std::unique_ptr<curl_slist, void (*)(curl_slist*)> header_guard(header_list,
                                                                          &curl_slist_free_all);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, header_list);

    const CURLcode code = curl_easy_perform(curl);
    if (code != CURLE_OK) {
        const char* detail = error_buffer[0] != '\0' ? error_buffer : curl_easy_strerror(code);
        throw TransportFailure{detail};
    }

    long status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    response.status = static_cast<int>(status);
    return response;
}

/// Parse an HTTP-date via libcurl (RFC 9110 Retry-After date form).
inline std::optional<double> seconds_until_http_date(const std::string& text, time_t now) {
    const time_t when = curl_getdate(text.c_str(), nullptr);
    if (when == static_cast<time_t>(-1)) {
        return std::nullopt;
    }
    return std::max(0.0, static_cast<double>(when - now));
}

} // namespace myairtable
