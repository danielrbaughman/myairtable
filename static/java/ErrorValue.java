// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Airtable's representation of a computed-field error. JSON shape: {@code {"error": "#ERROR!"}}.
 * Only the object form is accepted/emitted.
 */
public record ErrorValue(@JsonProperty("error") String error) {}
