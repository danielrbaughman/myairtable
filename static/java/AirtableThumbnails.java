// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/** Attachment thumbnail variants ({@code small}, {@code large}, {@code full}). */
public record AirtableThumbnails(Thumbnail small, Thumbnail large, Thumbnail full) {

  /** A single thumbnail rendition. */
  public record Thumbnail(String url, Long width, Long height) {}
}
