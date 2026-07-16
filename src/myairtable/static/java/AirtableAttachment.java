// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Airtable attachment (file/image) as returned in field values.
 *
 * <p>Mutable POJO (not a record) so upload-side construction stays ergonomic: to attach a file,
 * create one and set only {@code url} (and optionally {@code filename}) — Airtable ingests the URL
 * and fills in the rest.
 */
public final class AirtableAttachment {
  private String id;
  private String url;
  private String filename;
  private Long size;
  private String type;
  private AirtableThumbnails thumbnails;

  public AirtableAttachment() {}

  /** Upload-side convenience: an attachment to be ingested from {@code url}. */
  public AirtableAttachment(String url) {
    this.url = url;
  }

  public String getId() {
    return id;
  }

  public void setId(String id) {
    this.id = id;
  }

  public String getUrl() {
    return url;
  }

  public void setUrl(String url) {
    this.url = url;
  }

  public String getFilename() {
    return filename;
  }

  public void setFilename(String filename) {
    this.filename = filename;
  }

  public Long getSize() {
    return size;
  }

  public void setSize(Long size) {
    this.size = size;
  }

  public String getType() {
    return type;
  }

  public void setType(String type) {
    this.type = type;
  }

  public AirtableThumbnails getThumbnails() {
    return thumbnails;
  }

  public void setThumbnails(AirtableThumbnails thumbnails) {
    this.thumbnails = thumbnails;
  }
}
