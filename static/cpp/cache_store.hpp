#pragma once

#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

namespace myairtable {

/// A TTL + LRU response cache keyed by (table_id, cache_key), guarded by a
/// std::mutex with a split-lock check-fetch-store: the cache is checked under
/// the lock, RELEASED for the HTTP fetch (unrelated reads are never serialized
/// behind one in-flight request), then re-acquired to store. Disabled
/// (pass-through) when ttl_seconds <= 0.
class CacheStore {
  public:
    explicit CacheStore(double ttl_seconds = 0.0, size_t max_entries = 1000)
        : ttl_seconds_(ttl_seconds), max_entries_(max_entries) {}

    CacheStore(const CacheStore&) = delete;
    CacheStore& operator=(const CacheStore&) = delete;

    double ttl_seconds() const { return ttl_seconds_; }
    bool enabled() const { return ttl_seconds_ > 0.0; }

    /// Return the cached payload, or run `fetch` and cache the result. When
    /// `should_cache` returns false for a fetched payload it is returned but
    /// NOT stored (e.g. a list page carrying a transient `offset` continuation
    /// token must never be cached — the token expires server-side).
    std::string get_or_add(const std::string& table_id, const std::string& cache_key,
                           const std::function<std::string()>& fetch,
                           const std::function<bool(const std::string&)>& should_cache = {}) {
        if (!enabled()) {
            return fetch();
        }
        const Key key{table_id, cache_key};
        {
            std::lock_guard<std::mutex> guard(mutex_);
            if (const auto it = entries_.find(key);
                it != entries_.end() && it->second.expiry > Clock::now()) {
                it->second.seq = ++seq_;
                return it->second.value;
            }
        }
        // Fetch OUTSIDE the lock (split-lock: never hold a mutex across I/O).
        std::string value = fetch();
        if (should_cache && !should_cache(value)) {
            return value;
        }
        {
            std::lock_guard<std::mutex> guard(mutex_);
            entries_[key] = Entry{value, Clock::now() + to_duration(ttl_seconds_), ++seq_};
            evict_if_needed();
        }
        return value;
    }

    /// Peek a cached value, lazily evicting past-TTL entries — nullopt on miss
    /// or expiry. A non-nullopt result proves the entry was live (never stale).
    std::optional<std::string> get(const std::string& table_id, const std::string& cache_key) {
        const Key key{table_id, cache_key};
        std::lock_guard<std::mutex> guard(mutex_);
        if (const auto it = entries_.find(key); it != entries_.end()) {
            if (it->second.expiry > Clock::now()) {
                return it->second.value;
            }
            entries_.erase(it); // lazy eviction past TTL
        }
        return std::nullopt;
    }

    /// Drop every cached entry for one table (call after a mutation to it).
    void invalidate(const std::string& table_id) {
        std::lock_guard<std::mutex> guard(mutex_);
        for (auto it = entries_.begin(); it != entries_.end();) {
            if (it->first.first == table_id) {
                it = entries_.erase(it);
            } else {
                ++it;
            }
        }
    }

    void invalidate_all() {
        std::lock_guard<std::mutex> guard(mutex_);
        entries_.clear();
    }

    size_t size() {
        std::lock_guard<std::mutex> guard(mutex_);
        return entries_.size();
    }

  private:
    using Clock = std::chrono::steady_clock;
    using Key = std::pair<std::string, std::string>;

    struct Entry {
        std::string value;
        Clock::time_point expiry;
        uint64_t seq = 0;
    };

    static Clock::duration to_duration(double seconds) {
        return std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
    }

    /// LRU eviction: drop the lowest-seq (least recently used) entry while over
    /// capacity. Called under the lock.
    void evict_if_needed() {
        while (entries_.size() > max_entries_) {
            auto oldest = entries_.begin();
            for (auto it = entries_.begin(); it != entries_.end(); ++it) {
                if (it->second.seq < oldest->second.seq) {
                    oldest = it;
                }
            }
            entries_.erase(oldest);
        }
    }

    std::mutex mutex_;
    std::map<Key, Entry> entries_;
    double ttl_seconds_;
    size_t max_entries_;
    uint64_t seq_ = 0;
};

} // namespace myairtable
