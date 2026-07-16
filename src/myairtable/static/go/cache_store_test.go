package airtable

// G9.1 — White-box unit tests for cacheStore: the TTL read cache backing the
// client. These run offline and exercise the package-private store directly,
// mirroring the behavioral cases asserted end-to-end in the live caching suite
// (and the Java/Kotlin/Rust TestCaching parity refs).

import (
	"testing"
	"time"
)

func TestCacheStoreGetSetRoundTrip(t *testing.T) {
	c := newCacheStore(time.Minute)
	c.set("tbl1", "rec:abc", []byte(`{"id":"abc"}`))

	data, ok := c.get("tbl1", "rec:abc")
	if !ok {
		t.Fatal("expected a cache hit after set")
	}
	if string(data) != `{"id":"abc"}` {
		t.Fatalf("get returned %q, want the stored bytes", data)
	}
}

func TestCacheStoreMiss(t *testing.T) {
	c := newCacheStore(time.Minute)
	c.set("tbl1", "rec:abc", []byte(`x`))

	if _, ok := c.get("tbl1", "rec:missing"); ok {
		t.Fatal("expected a miss for an unknown key")
	}
	if _, ok := c.get("tblOther", "rec:abc"); ok {
		t.Fatal("expected a miss for a key under a different table")
	}
}

func TestCacheStoreTTLExpiryLazyEviction(t *testing.T) {
	// A tiny TTL plus a real wait drives the lazy-eviction path in get(): an
	// entry past its expiry returns (nil, false) and is deleted on access.
	c := newCacheStore(20 * time.Millisecond)
	c.set("tbl1", "rec:abc", []byte(`v`))

	if _, ok := c.get("tbl1", "rec:abc"); !ok {
		t.Fatal("entry should be live immediately after set")
	}

	time.Sleep(40 * time.Millisecond)

	if _, ok := c.get("tbl1", "rec:abc"); ok {
		t.Fatal("entry past its TTL must not be served")
	}
	// Lazy eviction: the expired entry is removed from the backing map, not just
	// hidden by the timestamp check.
	c.mu.RLock()
	_, present := c.entries["tbl1"]["rec:abc"]
	c.mu.RUnlock()
	if present {
		t.Fatal("expired entry should be evicted from the map on access")
	}
}

func TestCacheStoreInvalidateTableWipesOneTable(t *testing.T) {
	c := newCacheStore(time.Minute)
	c.set("tblA", "k1", []byte(`a`))
	c.set("tblA", "k2", []byte(`a2`))
	c.set("tblB", "k1", []byte(`b`))

	c.invalidateTable("tblA")

	if _, ok := c.get("tblA", "k1"); ok {
		t.Fatal("tblA k1 should be gone after invalidateTable")
	}
	if _, ok := c.get("tblA", "k2"); ok {
		t.Fatal("tblA k2 should be gone after invalidateTable")
	}
	if _, ok := c.get("tblB", "k1"); !ok {
		t.Fatal("tblB should be untouched by invalidateTable(tblA)")
	}
}

func TestCacheStoreInvalidateAllWipesEverything(t *testing.T) {
	c := newCacheStore(time.Minute)
	c.set("tblA", "k1", []byte(`a`))
	c.set("tblB", "k1", []byte(`b`))

	c.invalidateAll()

	if _, ok := c.get("tblA", "k1"); ok {
		t.Fatal("tblA should be gone after invalidateAll")
	}
	if _, ok := c.get("tblB", "k1"); ok {
		t.Fatal("tblB should be gone after invalidateAll")
	}
}

func TestCacheStoreEnabled(t *testing.T) {
	if (*cacheStore)(nil).enabled() {
		t.Fatal("nil cacheStore must report disabled")
	}
	if newCacheStore(0).enabled() {
		t.Fatal("zero-TTL cacheStore must report disabled")
	}
	if !newCacheStore(time.Second).enabled() {
		t.Fatal("positive-TTL cacheStore must report enabled")
	}
}

func TestCacheStoreDisabledIsNoOp(t *testing.T) {
	// A zero-TTL store is the default-off path: set never stores and get never
	// hits, so reads always fall through to the network.
	c := newCacheStore(0)
	c.set("tbl1", "k", []byte(`v`))
	if _, ok := c.get("tbl1", "k"); ok {
		t.Fatal("a disabled (zero-TTL) store must never serve a hit")
	}

	// The invalidate methods must tolerate a nil store (the no-cache client wires
	// a nil *cacheStore and still calls invalidateTable after mutations).
	var nilStore *cacheStore
	nilStore.invalidateTable("tbl1") // must not panic
	nilStore.invalidateAll()         // must not panic
	if _, ok := nilStore.get("tbl1", "k"); ok {
		t.Fatal("nil store get must report a miss")
	}
}
