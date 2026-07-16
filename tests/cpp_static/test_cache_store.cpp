// CacheStore TTL/LRU/scope semantics (Java TestCacheStore parity, 10 cases).
#include <catch2/catch_test_macros.hpp>

#include <chrono>
#include <thread>

#include "cache_store.hpp"

using namespace myairtable;

namespace {
std::function<std::string()> counting_fetch(int& calls, std::string value = "payload") {
    return [&calls, value] {
        ++calls;
        return value;
    };
}
} // namespace

TEST_CASE("disabled cache (ttl 0) passes every call through", "[cache]") {
    CacheStore cache(0.0);
    int calls = 0;
    cache.get_or_add("tbl", "k", counting_fetch(calls));
    cache.get_or_add("tbl", "k", counting_fetch(calls));
    REQUIRE(calls == 2);
    REQUIRE_FALSE(cache.enabled());
}

TEST_CASE("hit within ttl skips the fetch", "[cache]") {
    CacheStore cache(60.0);
    int calls = 0;
    REQUIRE(cache.get_or_add("tbl", "k", counting_fetch(calls)) == "payload");
    REQUIRE(cache.get_or_add("tbl", "k", counting_fetch(calls)) == "payload");
    REQUIRE(calls == 1);
}

TEST_CASE("expiry refetches", "[cache]") {
    CacheStore cache(0.03);
    int calls = 0;
    cache.get_or_add("tbl", "k", counting_fetch(calls));
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    cache.get_or_add("tbl", "k", counting_fetch(calls));
    REQUIRE(calls == 2);
}

TEST_CASE("peek returns live entries only and lazily evicts", "[cache]") {
    CacheStore cache(0.03);
    int calls = 0;
    cache.get_or_add("tbl", "k", counting_fetch(calls));
    REQUIRE(cache.get("tbl", "k") == "payload");
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    REQUIRE(cache.get("tbl", "k") == std::nullopt);
    REQUIRE(cache.size() == 0); // lazily evicted
}

TEST_CASE("invalidate is table-scoped", "[cache]") {
    CacheStore cache(60.0);
    int calls = 0;
    cache.get_or_add("tblA", "k", counting_fetch(calls));
    cache.get_or_add("tblB", "k", counting_fetch(calls));
    cache.invalidate("tblA");
    REQUIRE(cache.get("tblA", "k") == std::nullopt);
    REQUIRE(cache.get("tblB", "k") == "payload");
}

TEST_CASE("invalidate_all clears everything", "[cache]") {
    CacheStore cache(60.0);
    int calls = 0;
    cache.get_or_add("tblA", "k1", counting_fetch(calls));
    cache.get_or_add("tblB", "k2", counting_fetch(calls));
    cache.invalidate_all();
    REQUIRE(cache.size() == 0);
}

TEST_CASE("should_cache=false returns but never stores", "[cache]") {
    CacheStore cache(60.0);
    int calls = 0;
    const auto never = [](const std::string&) { return false; };
    REQUIRE(cache.get_or_add("tbl", "k", counting_fetch(calls), never) == "payload");
    REQUIRE(cache.get("tbl", "k") == std::nullopt);
    cache.get_or_add("tbl", "k", counting_fetch(calls), never);
    REQUIRE(calls == 2);
}

TEST_CASE("lru evicts the least recently used entry beyond capacity", "[cache]") {
    CacheStore cache(60.0, /*max_entries=*/2);
    int calls = 0;
    cache.get_or_add("tbl", "a", counting_fetch(calls, "A"));
    cache.get_or_add("tbl", "b", counting_fetch(calls, "B"));
    cache.get_or_add("tbl", "a", counting_fetch(calls, "A")); // refresh a
    cache.get_or_add("tbl", "c", counting_fetch(calls, "C")); // evicts b (LRU)
    REQUIRE(cache.get("tbl", "a") == "A");
    REQUIRE(cache.get("tbl", "b") == std::nullopt);
    REQUIRE(cache.get("tbl", "c") == "C");
}

TEST_CASE("distinct keys under one table are independent", "[cache]") {
    CacheStore cache(60.0);
    int calls = 0;
    cache.get_or_add("tbl", "k1", counting_fetch(calls, "one"));
    cache.get_or_add("tbl", "k2", counting_fetch(calls, "two"));
    REQUIRE(calls == 2);
    REQUIRE(cache.get("tbl", "k1") == "one");
    REQUIRE(cache.get("tbl", "k2") == "two");
}

TEST_CASE("fetch runs outside the lock (reentrant fetch cannot deadlock)", "[cache]") {
    CacheStore cache(60.0);
    // A fetch that itself reads the cache would deadlock if the lock were held
    // across it — split-lock semantics make this safe.
    const auto nested = [&cache]() -> std::string {
        return cache.get_or_add("other", "inner", [] { return std::string("inner"); });
    };
    REQUIRE(cache.get_or_add("tbl", "outer", nested) == "inner");
}
