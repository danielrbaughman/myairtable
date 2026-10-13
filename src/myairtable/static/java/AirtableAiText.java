// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Airtable AI text field — the generated text and where its generation stands. {@code state} is
 * {@code empty}, {@code loading}, {@code generated} or {@code error}; {@code errorType} is set only
 * for {@code error}.
 */
public record AirtableAiText(
    @JsonProperty("state") String state,
    @JsonProperty("isStale") Boolean isStale,
    @JsonProperty("value") String value,
    @JsonProperty("errorType") String errorType) {}
