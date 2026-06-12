// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Implemented by every generated {@code {Table}View} enum, exposing the view's Airtable ID ({@code
 * viwXXXXXXXXXXXXXX}). Lets {@link AirtableQuery#withView} accept a view constant directly — no
 * reaching for {@code .getId()} at the call site.
 */
public interface AirtableView {
  /** The Airtable view ID. */
  String getId();
}
