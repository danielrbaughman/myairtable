// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import java.time.Instant;

/**
 * Wrapping envelope for an Airtable record as returned by the API: {@code {"id": "recXXX",
 * "createdTime": "2024-...", "fields": {...}}}.
 */
public record AirtableRecord<T>(String id, Instant createdTime, T fields) {}
