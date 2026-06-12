// ==========================================
// MyAirtable static runtime.
// ==========================================

package myairtable;

/**
 * Airtable collaborator (user/account).
 *
 * <p>Mutable POJO so write-side construction stays ergonomic: to set a collaborator field, create
 * one and set only {@code id} (or {@code email}).
 */
public final class AirtableCollaborator {
  private String id;
  private String email;
  private String name;
  private String profilePicUrl;

  public AirtableCollaborator() {}

  /** Write-side convenience: a collaborator referenced by user ID. */
  public AirtableCollaborator(String id) {
    this.id = id;
  }

  public String getId() {
    return id;
  }

  public void setId(String id) {
    this.id = id;
  }

  public String getEmail() {
    return email;
  }

  public void setEmail(String email) {
    this.email = email;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public String getProfilePicUrl() {
    return profilePicUrl;
  }

  public void setProfilePicUrl(String profilePicUrl) {
    this.profilePicUrl = profilePicUrl;
  }
}
