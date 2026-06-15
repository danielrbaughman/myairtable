package airtable

// cacheStore is a TTL cache for read responses, keyed per table + query. It is
// safe for concurrent use. Entries expire lazily on read. A zero TTL disables
// caching entirely (the default).

import (
	"sync"
	"time"
)

type cacheEntry struct {
	data    []byte
	expires time.Time
}

type cacheStore struct {
	mu      sync.RWMutex
	ttl     time.Duration
	entries map[string]map[string]cacheEntry // tableID -> cacheKey -> entry
}

func newCacheStore(ttl time.Duration) *cacheStore {
	return &cacheStore{ttl: ttl, entries: map[string]map[string]cacheEntry{}}
}

func (c *cacheStore) enabled() bool { return c != nil && c.ttl > 0 }

// get returns cached bytes for (tableID, key) if present and unexpired.
func (c *cacheStore) get(tableID, key string) ([]byte, bool) {
	if !c.enabled() {
		return nil, false
	}
	c.mu.RLock()
	entry, ok := c.entries[tableID][key]
	c.mu.RUnlock()
	if !ok {
		return nil, false
	}
	if time.Now().After(entry.expires) {
		c.mu.Lock()
		delete(c.entries[tableID], key)
		c.mu.Unlock()
		return nil, false
	}
	return entry.data, true
}

// set stores bytes for (tableID, key) with the store's TTL.
func (c *cacheStore) set(tableID, key string, data []byte) {
	if !c.enabled() {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.entries[tableID] == nil {
		c.entries[tableID] = map[string]cacheEntry{}
	}
	c.entries[tableID][key] = cacheEntry{data: data, expires: time.Now().Add(c.ttl)}
}

// invalidateTable wipes all cached entries for a table (after a mutation).
func (c *cacheStore) invalidateTable(tableID string) {
	if c == nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, tableID)
}

// invalidateAll wipes the entire cache.
func (c *cacheStore) invalidateAll() {
	if c == nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries = map[string]map[string]cacheEntry{}
}
