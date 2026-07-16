// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Airtable's representation of a non-finite number. JSON shape: {@code {"specialValue": "NaN"}}.
 * Only the object form is accepted/emitted.
 */
public record SpecialNumber(@JsonProperty("specialValue") String specialValue) {}
