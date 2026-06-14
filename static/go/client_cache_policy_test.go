package airtable

// G9.2 — White-box tests for NewClient's cache policy: cacheSeconds <= 0 wires a
// nil/disabled cache (read caching off, the default), and a positive value wires
// an enabled store with the requested TTL. Verified offline by inspecting the
// package-private c.cache field — no network.

import (
	"testing"
	"time"
)

func TestNewClientZeroCacheSecondsDisablesCache(t *testing.T) {
	c := NewClient("key", "base", 0)
	if c.cache != nil {
		t.Fatal("cacheSeconds=0 should leave c.cache nil")
	}
	if c.cache.enabled() {
		t.Fatal("nil cache must report disabled")
	}
}

func TestNewClientNegativeCacheSecondsDisablesCache(t *testing.T) {
	c := NewClient("key", "base", -5)
	if c.cache != nil {
		t.Fatal("negative cacheSeconds should leave c.cache nil")
	}
	if c.cache.enabled() {
		t.Fatal("nil cache must report disabled")
	}
}

func TestNewClientPositiveCacheSecondsEnablesCache(t *testing.T) {
	c := NewClient("key", "base", 30)
	if c.cache == nil {
		t.Fatal("cacheSeconds=30 should construct a cache")
	}
	if !c.cache.enabled() {
		t.Fatal("a 30s cache must report enabled")
	}
	if got := c.cache.ttl; got != 30*time.Second {
		t.Fatalf("cache ttl = %s, want 30s", got)
	}
}

func TestNewClientFractionalCacheSeconds(t *testing.T) {
	// cacheSeconds is a float64; sub-second TTLs round-trip exactly.
	c := NewClient("key", "base", 1.5)
	if c.cache == nil || !c.cache.enabled() {
		t.Fatal("1.5s cache should be enabled")
	}
	if got := c.cache.ttl; got != 1500*time.Millisecond {
		t.Fatalf("cache ttl = %s, want 1.5s", got)
	}
}

func TestNewClientInvalidateOnDisabledCacheIsSafe(t *testing.T) {
	// The no-cache client still calls invalidate after every mutation; these must
	// be safe no-ops against the nil cache.
	c := NewClient("key", "base", 0)
	c.InvalidateAllCaches()        // must not panic
	c.InvalidateTableCache("tblX") // must not panic
}
