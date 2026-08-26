package myairtable;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.node.NullNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * myairtable-6q37.6 — the local {@code copy()} verb on generated ORM models.
 *
 * <p>{@code copy()} is the local half of the table's {@code duplicate(...)}: duplicate == fetch +
 * copy + create. It performs ZERO I/O, so unlike duplicate it is 100% hermetically testable, and
 * {@link CopyStubModel} below is a hand-written stand-in built to the EXACT shape {@code java.py}
 * emits for a table with writable, computed and attachment fields — same {@code @JsonIgnore}
 * plumbing, same writable-only {@code toCreateFields()}, same {@code copy()} body. Assertions here
 * therefore pin the generated code's contract; {@code tests/test_generators.py} pins that the
 * generator still emits it.
 *
 * <p>The load-bearing part is the detach, and on this target it is structural: a fresh instance
 * starts with a null id, a null createdTime and {@code snapshot = Map.of()}, so {@code copy()} only
 * has to NOT undo that (in particular, never call {@code takeSnapshot()}) and deliberately put the
 * client back.
 */
class TestCopyPayload {

  // ---- the stand-in model --------------------------------------------------

  /**
   * Stand-in for a generated {@code {Table}Model}, mirroring what java.py emits: writable fields
   * get setters, computed fields are getter-only (decode writes the private field directly), and
   * {@code toCreateFields()} is generated over the writable fields ONLY.
   */
  public static final class CopyStubModel implements AirtableModel {

    @JsonProperty("fldName")
    private String name;

    @JsonProperty("fldTags")
    private List<String> tags;

    @JsonProperty("fldPhotos")
    private List<AirtableAttachment> photos;

    @JsonProperty("fldLinks")
    private List<String> links;

    @JsonProperty("fldPeople")
    private List<AirtableCollaborator> people;

    /** An unmodelled cell: Jackson decodes it to an editable ObjectNode/ArrayNode. */
    @JsonProperty("fldExtra")
    private JsonNode extra;

    // Computed fields below: no setter exists, by construction.

    @JsonProperty("fldComputed")
    @JsonDeserialize(using = MaybeSpecialOrErrorDeserializer.class)
    private MaybeSpecialOrError<String> computedText;

    /**
     * A computed cell that happens to hold the attachment SHAPE — a lookup of the linked record's
     * attachment field. Never written back, so {@code copy()} must leave its id/size/type alone
     * rather than projecting it.
     */
    @JsonProperty("fldLookupPhotos")
    @JsonDeserialize(using = VecOrValueDeserializer.class)
    private VecOrValue<MaybeSpecialOrError<AirtableAttachment>> lookupPhotos;

    @JsonIgnore private String id;
    @JsonIgnore private Instant createdTime;
    @JsonIgnore private AirtableClient attachedClient;
    @JsonIgnore private Map<String, JsonNode> snapshot = Map.of();

    public CopyStubModel() {}

    public String getName() {
      return name;
    }

    public void setName(String value) {
      this.name = value;
    }

    public List<String> getTags() {
      return tags;
    }

    public void setTags(List<String> value) {
      this.tags = value;
    }

    public List<AirtableAttachment> getPhotos() {
      return photos;
    }

    public void setPhotos(List<AirtableAttachment> value) {
      this.photos = value;
    }

    public List<String> getLinks() {
      return links;
    }

    public void setLinks(List<String> value) {
      this.links = value;
    }

    public List<AirtableCollaborator> getPeople() {
      return people;
    }

    public void setPeople(List<AirtableCollaborator> value) {
      this.people = value;
    }

    public JsonNode getExtra() {
      return extra;
    }

    public void setExtra(JsonNode value) {
      this.extra = value;
    }

    public MaybeSpecialOrError<String> getComputedText() {
      return computedText;
    }

    public VecOrValue<MaybeSpecialOrError<AirtableAttachment>> getLookupPhotos() {
      return lookupPhotos;
    }

    @Override
    public String getTableId() {
      return "tblStub";
    }

    @Override
    public String getId() {
      return id;
    }

    @Override
    public void setId(String value) {
      this.id = value;
    }

    @Override
    public Instant getCreatedTime() {
      return createdTime;
    }

    @Override
    public void setCreatedTime(Instant value) {
      this.createdTime = value;
    }

    @Override
    public AirtableClient getAttachedClient() {
      return attachedClient;
    }

    @Override
    public void setAttachedClient(AirtableClient client) {
      this.attachedClient = client;
    }

    /** Writable fields only — the sole input to OrmTable.create. */
    @Override
    public Map<String, JsonNode> toCreateFields() {
      Map<String, JsonNode> fields = new LinkedHashMap<>();
      putIfNotNull(fields, "fldName", name);
      putIfNotNull(fields, "fldTags", tags);
      putIfNotNull(fields, "fldPhotos", photos);
      putIfNotNull(fields, "fldLinks", links);
      putIfNotNull(fields, "fldPeople", people);
      putIfNotNull(fields, "fldExtra", extra);
      return fields;
    }

    @Override
    public Map<String, JsonNode> toRecord() {
      Map<String, JsonNode> fields = toCreateFields();
      putIfNotNull(fields, "fldComputed", computedText);
      putIfNotNull(fields, "fldLookupPhotos", lookupPhotos);
      return fields;
    }

    @Override
    public void takeSnapshot() {
      snapshot = toCreateFields();
    }

    @Override
    public Map<String, JsonNode> dirtyFields() {
      Map<String, JsonNode> current = toCreateFields();
      Map<String, JsonNode> dirty = new LinkedHashMap<>();
      for (Map.Entry<String, JsonNode> entry : current.entrySet()) {
        if (!entry.getValue().equals(snapshot.get(entry.getKey()))) {
          dirty.put(entry.getKey(), entry.getValue());
        }
      }
      for (String key : snapshot.keySet()) {
        if (!current.containsKey(key)) {
          dirty.put(key, NullNode.getInstance());
        }
      }
      return dirty;
    }

    /** Byte-for-byte the body java.py emits (see {@code _java_copy_expression}). */
    public CopyStubModel copy() {
      CopyStubModel copied = new CopyStubModel();
      copied.name = name;
      copied.tags = AirtableModel.detachForCopy(tags);
      copied.photos = AirtableModel.projectAttachmentsForCopy(photos);
      copied.links = AirtableModel.detachForCopy(links);
      copied.people = AirtableModel.detachForCopy(people);
      copied.extra = AirtableModel.detachForCopy(extra);
      copied.computedText = AirtableModel.detachForCopy(computedText);
      copied.lookupPhotos = AirtableModel.detachForCopy(lookupPhotos);
      copied.attachedClient = attachedClient;
      return copied;
    }

    private static void putIfNotNull(Map<String, JsonNode> fields, String id, Object value) {
      if (value != null) {
        fields.put(id, AirtableRuntime.V(value));
      }
    }
  }

  // ---- fixtures ------------------------------------------------------------

  private static final Set<String> WRITABLE_KEYS =
      new LinkedHashSet<>(
          List.of("fldName", "fldTags", "fldPhotos", "fldLinks", "fldPeople", "fldExtra"));

  /** An attachment exactly as the server returns it: signed url plus read-only metadata. */
  private static AirtableAttachment serverAttachment(String id, String filename) {
    AirtableAttachment attachment = new AirtableAttachment("https://example.com/" + filename);
    attachment.setId(id);
    attachment.setFilename(filename);
    attachment.setSize(1234L);
    attachment.setType("image/png");
    attachment.setThumbnails(
        new AirtableThumbnails(
            new AirtableThumbnails.Thumbnail("https://example.com/small-" + filename, 36L, 36L),
            null,
            null));
    return attachment;
  }

  private static AirtableCollaborator collaborator(String id) {
    AirtableCollaborator person = new AirtableCollaborator(id);
    person.setEmail("someone@example.com");
    person.setName("Someone");
    return person;
  }

  private static ObjectNode extraNode() {
    ObjectNode node = AirtableJson.MAPPER.createObjectNode();
    node.put("choice", "a");
    return node;
  }

  /**
   * A record as it exists after a read: every field populated (computed included), an id, a
   * createdTime, an attached client and a snapshot taken. The mutable containers are deliberately
   * {@code ArrayList}s — that is what Jackson decodes into.
   */
  private static CopyStubModel savedRecord(AirtableClient client) {
    CopyStubModel model = new CopyStubModel();
    model.name = "original";
    model.tags = new ArrayList<>(List.of("a", "b"));
    model.photos = new ArrayList<>(List.of(serverAttachment("attOne0000000001", "one.png")));
    model.links = new ArrayList<>(List.of("recLinked00000001", "recLinked00000002"));
    model.people = new ArrayList<>(List.of(collaborator("usrOne0000000001")));
    model.extra = extraNode();
    model.computedText = new MaybeSpecialOrError.Value<>("computed");
    model.lookupPhotos =
        new VecOrValue.Multiple<>(
            new ArrayList<>(
                List.of(
                    new MaybeSpecialOrError.Value<>(
                        serverAttachment("attLook000000001", "look.png")))));
    model.id = "recSource00000001";
    model.createdTime = Instant.parse("2026-01-01T00:00:00Z");
    model.attachedClient = client;
    model.takeSnapshot();
    return model;
  }

  private static CopyStubModel savedRecord() {
    return savedRecord(null);
  }

  /** The single attachment inside the computed lookup cell. */
  private static AirtableAttachment lookupPhoto(CopyStubModel model) {
    VecOrValue.Multiple<MaybeSpecialOrError<AirtableAttachment>> multiple =
        (VecOrValue.Multiple<MaybeSpecialOrError<AirtableAttachment>>) model.getLookupPhotos();
    return multiple.values().get(0).value();
  }

  // ---- the detach ----------------------------------------------------------

  @Nested
  class Detach {

    @Test
    void copyClearsRecordIdentity() {
      CopyStubModel copied = savedRecord().copy();

      assertNull(copied.getId(), "a carried id would make the copy an EDIT of its source");
      assertNull(
          copied.getCreatedTime(), "createdTime is server-assigned; an unsaved model has none");
      assertTrue(copied.isNew(), "isNew() is derived from id, so the copy must report as new");
    }

    @Test
    void copyStartsWithAnEmptySnapshotSoItPostsEverything() {
      // The silent-failure trap the other ports hit: a copy that carried the source's
      // snapshot would diff to nothing. Here the source itself demonstrates it —
      // freshly snapshotted, its own dirtyFields() is empty — while the copy's full
      // writable set is intact.
      CopyStubModel source = savedRecord();
      assertTrue(source.dirtyFields().isEmpty(), "sanity: a just-snapshotted record has no diff");

      CopyStubModel copied = source.copy();
      assertEquals(
          WRITABLE_KEYS,
          copied.dirtyFields().keySet(),
          "copy() must NOT call takeSnapshot(): everything is new on an unsaved model");
      assertEquals(copied.toCreateFields(), copied.dirtyFields());
    }

    @Test
    void copyKeepsTheAttachedClientSoItCanSaveItself() {
      AirtableClient client = new AirtableClient("appX", "key");
      CopyStubModel copied = savedRecord(client).copy();

      assertSame(
          client,
          copied.getAttachedClient(),
          "contract item 4: the client handle is KEPT, so create/save works");
      assertSame(client, copied.requireAttachedClient());
    }

    @Test
    void copyOfACopyIsStillDetached() {
      CopyStubModel once = savedRecord().copy();
      once.setName("renamed");
      CopyStubModel twice = once.copy();

      assertNull(twice.getId());
      assertEquals("renamed", twice.getName());
      assertEquals(WRITABLE_KEYS, twice.dirtyFields().keySet());
    }
  }

  // ---- computed values -----------------------------------------------------

  @Nested
  class ComputedValues {

    @Test
    void computedValuesAreCarriedSoTheCopyReadsLikeItsSource() {
      CopyStubModel copied = savedRecord().copy();

      assertEquals("computed", copied.getComputedText().value());
      assertEquals("look.png", lookupPhoto(copied).getFilename());
    }

    @Test
    void computedValuesNeverReachTheCreatePayload() {
      // Safe by construction on this target: toCreateFields() is generated over the
      // writable fields only (java.py), and it is the sole input to OrmTable.create
      // (OrmTable.java:192). A computed field in a create body is a 422.
      Map<String, JsonNode> payload = savedRecord().copy().toCreateFields();

      assertEquals(WRITABLE_KEYS, payload.keySet());
      assertFalse(payload.containsKey("fldComputed"));
      assertFalse(payload.containsKey("fldLookupPhotos"));
    }

    @Test
    void computedWrappersAreRebuiltNotAliased() {
      // MaybeSpecialOrError/VecOrValue are records, but their payload need not be: this
      // lookup holds mutable AirtableAttachment POJOs behind a mutable ArrayList.
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      assertNotSame(source.getLookupPhotos(), copied.getLookupPhotos());
      assertNotSame(lookupPhoto(source), lookupPhoto(copied));
    }
  }

  // ---- attachments ---------------------------------------------------------

  @Nested
  class Attachments {

    @Test
    void writableAttachmentsAreProjectedToUrlAndFilename() {
      AirtableAttachment photo = savedRecord().copy().getPhotos().get(0);

      assertEquals("https://example.com/one.png", photo.getUrl());
      assertEquals("one.png", photo.getFilename());
      assertNull(
          photo.getId(), "create rejects a server attachment id (INVALID_ATTACHMENT_OBJECT)");
      assertNull(photo.getSize());
      assertNull(photo.getType());
      assertNull(photo.getThumbnails());
    }

    @Test
    void projectedAttachmentsSerializeToExactlyUrlAndFilename() {
      // The wire check: the mapper omits nulls, so the create body carries the two-key
      // object Airtable's whitelist accepts and nothing else.
      JsonNode encoded = savedRecord().copy().toCreateFields().get("fldPhotos").get(0);

      Set<String> keys = new LinkedHashSet<>();
      for (Iterator<String> it = encoded.fieldNames(); it.hasNext(); ) {
        keys.add(it.next());
      }
      assertEquals(Set.of("url", "filename"), keys);
    }

    @Test
    void computedAttachmentShapedCellsKeepTheirFullMetadata() {
      // A lookup can hold the same shape as an attachment cell, but it is never written
      // back — stripping its metadata would lose fidelity for nothing.
      AirtableAttachment lookup = lookupPhoto(savedRecord().copy());

      assertEquals("attLook000000001", lookup.getId());
      assertEquals(1234L, lookup.getSize());
      assertEquals("image/png", lookup.getType());
      assertEquals("https://example.com/small-look.png", lookup.getThumbnails().small().url());
    }
  }

  // ---- no shared mutable state ---------------------------------------------

  @Nested
  class NoSharedState {

    @Test
    void containersAreRebuiltNotAliased() {
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      assertNotSame(source.getTags(), copied.getTags(), "a shared list would leak mutations");
      assertNotSame(source.getPhotos(), copied.getPhotos());
      assertNotSame(source.getLinks(), copied.getLinks());
      assertNotSame(source.getPeople(), copied.getPeople());
      assertNotSame(source.getExtra(), copied.getExtra());
    }

    @Test
    void mutablePojoCellsAreClonedNotAliased() {
      // AirtableAttachment and AirtableCollaborator are deliberately mutable POJOs
      // (write-side ergonomics), so rebuilding the list alone would not be enough.
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      assertNotSame(source.getPhotos().get(0), copied.getPhotos().get(0));
      assertNotSame(source.getPeople().get(0), copied.getPeople().get(0));

      copied.getPeople().get(0).setEmail("changed@example.com");
      copied.getPhotos().get(0).setUrl("https://example.com/changed.png");

      assertEquals("someone@example.com", source.getPeople().get(0).getEmail());
      assertEquals("https://example.com/one.png", source.getPhotos().get(0).getUrl());
    }

    @Test
    void jsonNodeCellsAreDeepCopied() {
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      ((ObjectNode) copied.getExtra()).put("choice", "b");

      assertEquals("a", source.getExtra().get("choice").asText());
      assertEquals("b", copied.getExtra().get("choice").asText());
    }

    @Test
    void mutatingTheSourcesOwnListDoesNotReachTheCopy() {
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      source.getTags().add("c");

      assertEquals(List.of("a", "b"), copied.getTags());
      assertEquals(List.of("a", "b", "c"), source.getTags());
    }

    @Test
    void mutatingTheCopyLeavesTheSourceAlone() {
      CopyStubModel source = savedRecord();
      CopyStubModel copied = source.copy();

      copied.setName("renamed");
      copied.setTags(List.of("z"));
      copied.setLinks(List.of("recSomethingElse1"));
      copied.setPhotos(List.of());

      assertEquals("original", source.getName());
      assertEquals(List.of("a", "b"), source.getTags());
      assertEquals(List.of("recLinked00000001", "recLinked00000002"), source.getLinks());
      assertEquals(1, source.getPhotos().size());
    }

    @Test
    void copyLeavesTheSourceCompletelyUntouched() {
      AirtableClient client = new AirtableClient("appX", "key");
      CopyStubModel source = savedRecord(client);
      Map<String, JsonNode> before = source.toRecord();

      source.copy();

      assertEquals("recSource00000001", source.getId());
      assertEquals(Instant.parse("2026-01-01T00:00:00Z"), source.getCreatedTime());
      assertSame(client, source.getAttachedClient());
      assertTrue(source.dirtyFields().isEmpty(), "copy() must not disturb the source's snapshot");
      assertEquals(before, source.toRecord());
      // Notably the source's own attachment keeps its server metadata: the projection
      // happens on the way OUT, into the copy.
      assertEquals("attOne0000000001", source.getPhotos().get(0).getId());
    }
  }

  // ---- I/O -----------------------------------------------------------------

  @Nested
  class NoIO {

    private AirtableClient clientWith(FakeTransport transport) {
      return new AirtableClient(
          "appX",
          "key",
          "https://api.airtable.com/v0",
          new CacheStore(),
          3,
          0.01,
          0.05,
          30.0,
          transport);
    }

    @Test
    void copyPerformsNoIO() {
      // Nothing in copy() may touch the transport — that is the entire difference from
      // the table's duplicate(), which re-reads the source from Airtable first.
      FakeTransport transport =
          new FakeTransport(
              (request, callIndex) -> {
                throw new AssertionError("copy() must not make any HTTP request");
              });
      AirtableClient client = clientWith(transport);

      savedRecord(client).copy().copy();

      assertEquals(0, transport.callCount());
      assertTrue(transport.requestHistory().isEmpty());
    }

    @Test
    void creatingACopySendsAPostWithTheProjectedWritableSet() throws Exception {
      FakeTransport transport =
          new FakeTransport(
              (request, callIndex) ->
                  FakeTransport.Canned.ok(
                      "{\"records\": [{\"id\": \"recNew00000000001\", \"createdTime\":"
                          + " \"2026-02-02T00:00:00.000Z\", \"fields\": {\"fldName\":"
                          + " \"copied\"}}]}"));
      AirtableClient client = clientWith(transport);
      OrmTable<CopyStubModel> table = new OrmTable<>("tblStub", CopyStubModel.class, client);

      CopyStubModel copied = savedRecord(client).copy();
      copied.setName("copied");
      CopyStubModel created = table.create(copied);

      var request = transport.requestHistory().get(0);
      assertEquals(
          "POST", request.method(), "a carried id would have made this a PATCH of the source row");
      JsonNode body = AirtableJson.MAPPER.readTree(FakeTransport.bodyText(request));
      JsonNode fields = body.get("records").get(0).get("fields");

      Set<String> keys = new LinkedHashSet<>();
      for (Iterator<String> it = fields.fieldNames(); it.hasNext(); ) {
        keys.add(it.next());
      }
      assertEquals(WRITABLE_KEYS, keys, "computed fields must never reach the wire");
      assertEquals("copied", fields.get("fldName").asText());
      assertFalse(fields.get("fldPhotos").get(0).has("id"));
      assertEquals("recNew00000000001", created.getId());
    }
  }
}
