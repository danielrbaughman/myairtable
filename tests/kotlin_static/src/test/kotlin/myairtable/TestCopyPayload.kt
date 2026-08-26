package myairtable

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

// myairtable-6q37.7 — the local `copy()` verb on generated ORM models.
//
// copy() is the local half of duplicate(): duplicate == fetch + copy + create.
// It performs ZERO I/O, so it is 100% hermetically testable, and the model below
// is a hand-written stand-in built to the EXACT shape kotlin.py emits for a table
// with writable, computed and attachment fields — same @Transient members, same
// writable-only toCreateFields(), same copy() body. Assertions here therefore pin
// the generated code's contract; test_generators.py pins that the generator still
// emits it.
//
// The load-bearing part is the detach, and on this target it is structural: a
// fresh instance already has id = null, createdTime = null and an empty snapshot,
// so copy() only has to NOT undo that (in particular, never call takeSnapshot()) and
// deliberately put the client back.

/** Stand-in for a generated `{Table}Model`, mirroring kotlin.py's emitted shape. */
@Serializable
private class CopyStubModel(
    // Writable fields: `var`, in the primary constructor, defaulting to null.
    @SerialName("fldName") var name: String? = null,
    @SerialName("fldTags") var tags: List<String>? = null,
    @SerialName("fldPhotos") var photos: List<AirtableAttachment>? = null,
    @SerialName("fldLinks") var links: List<RecordId>? = null,
    // Computed fields: `val`, server-owned, never in a create body.
    @SerialName("fldComputed") val computedText: MaybeSpecialOrError<String>? = null,
    // A computed cell that happens to hold the attachment SHAPE — a lookup of the
    // linked record's attachment field. Never written back, so copy() must leave its
    // id/size/type alone rather than projecting it.
    @SerialName("fldLookupPhotos") val lookupPhotos: List<AirtableAttachment>? = null,
) : AirtableModel {
    companion object {
        const val TABLE_ID: String = "tblStub"
    }

    @Transient
    override var id: RecordId? = null

    @Transient
    override var createdTime: Instant? = null

    @Transient
    override var attachedClient: AirtableClient? = null

    @Transient
    private var snapshot: Map<String, JsonElement> = emptyMap()

    override val tableId: String get() = TABLE_ID

    override fun toCreateFields(): Map<String, JsonElement> =
        buildMap {
            name?.let { put("fldName", V(it)) }
            tags?.let { put("fldTags", V(it)) }
            photos?.let { put("fldPhotos", V(it)) }
            links?.let { put("fldLinks", V(it)) }
        }

    override fun toRecord(): Map<String, JsonElement> =
        buildMap {
            name?.let { put("fldName", V(it)) }
            tags?.let { put("fldTags", V(it)) }
            photos?.let { put("fldPhotos", V(it)) }
            links?.let { put("fldLinks", V(it)) }
            computedText?.let { put("fldComputed", V(it)) }
            lookupPhotos?.let { put("fldLookupPhotos", V(it)) }
        }

    override fun takeSnapshot() {
        snapshot = toCreateFields()
    }

    override fun dirtyFields(): Map<String, JsonElement> {
        val current = toCreateFields()
        val dirty = mutableMapOf<String, JsonElement>()
        for ((key, value) in current) if (snapshot[key] != value) dirty[key] = value
        for (key in snapshot.keys) if (key !in current) dirty[key] = JsonNull
        return dirty
    }

    fun copy(): CopyStubModel {
        val copied =
            CopyStubModel(
                name = name,
                tags = tags?.toList(),
                photos = projectAttachmentsForCopy(photos),
                links = links?.toList(),
                computedText = computedText,
                lookupPhotos = lookupPhotos?.toList(),
            )
        copied.attachedClient = attachedClient
        return copied
    }
}

class TestCopyPayload {
    /** An attachment exactly as the server returns it: signed url plus read-only metadata. */
    private fun serverAttachment(
        id: String,
        filename: String,
    ) = AirtableAttachment(
        id = id,
        url = "https://example.com/$filename",
        filename = filename,
        size = 1234L,
        type = "image/png",
        thumbnails = AirtableThumbnails(small = AirtableThumbnails.Thumbnail(url = "https://example.com/small-$filename")),
    )

    /**
     * A record as it exists after a read: every field populated (computed included),
     * an id, a createdTime, an attached client and a snapshot taken.
     */
    private fun savedRecord(client: AirtableClient? = null): CopyStubModel =
        CopyStubModel(
            name = "original",
            tags = mutableListOf("a", "b"),
            photos = mutableListOf(serverAttachment("attOne0000000001", "one.png")),
            links = mutableListOf("recLinked00000001", "recLinked00000002"),
            computedText = MaybeSpecialOrError.Value("computed"),
            lookupPhotos = mutableListOf(serverAttachment("attLook000000001", "look.png")),
        ).apply {
            id = "recSource00000001"
            createdTime = Instant.parse("2026-01-01T00:00:00Z")
            attachedClient = client
            takeSnapshot()
        }

    // region the detach

    @Test
    fun copyClearsRecordIdentity() {
        val copied = savedRecord().copy()

        assertNull(copied.id, "a carried id would make the copy an EDIT of its source")
        assertNull(copied.createdTime, "createdTime is server-assigned; an unsaved model has none")
        assertTrue(copied.isNew, "isNew is derived from id, so the copy must report as new")
    }

    @Test
    fun copyStartsWithAnEmptySnapshotSoItPostsEverything() {
        // The silent-failure trap other targets hit: a copy that carried the source's
        // snapshot would diff to nothing. Here the source itself demonstrates it —
        // freshly snapshotted, its own dirtyFields() is empty — while the copy's full
        // writable set is intact.
        val source = savedRecord()
        assertTrue(source.dirtyFields().isEmpty(), "sanity: a just-snapshotted record has no diff")

        val copied = source.copy()
        assertEquals(
            setOf("fldName", "fldTags", "fldPhotos", "fldLinks"),
            copied.dirtyFields().keys,
            "copy() must NOT call takeSnapshot(): everything is new on an unsaved model",
        )
        assertEquals(copied.toCreateFields(), copied.dirtyFields())
    }

    @Test
    fun copyKeepsTheAttachedClientSoItCanSaveItself() {
        val client = AirtableClient(baseId = "appX", apiKey = "key")
        client.use {
            val copied = savedRecord(client).copy()
            assertSame(client, copied.attachedClient, "contract item 4: the client handle is KEPT, so create/save works")
        }
    }

    @Test
    fun copyOfACopyIsStillDetached() {
        val twice = savedRecord().copy().apply { name = "renamed" }.copy()

        assertNull(twice.id)
        assertEquals("renamed", twice.name)
    }

    // endregion

    // region computed values

    @Test
    fun computedValuesAreCarriedSoTheCopyReadsLikeItsSource() {
        val copied = savedRecord().copy()

        assertEquals("computed", copied.computedText.value)
        assertEquals(1, copied.lookupPhotos?.size)
    }

    @Test
    fun computedValuesNeverReachTheCreatePayload() {
        // Safe by construction on this target: toCreateFields() is generated over the
        // writable fields only (kotlin.py), and it is the sole input to OrmTable.create.
        val payload = savedRecord().copy().toCreateFields()

        assertEquals(setOf("fldName", "fldTags", "fldPhotos", "fldLinks"), payload.keys)
        assertFalse("fldComputed" in payload, "a computed field in a create body is a 422 (INVALID_VALUE_FOR_COLUMN)")
        assertFalse("fldLookupPhotos" in payload)
    }

    // endregion

    // region attachments

    @Test
    fun writableAttachmentsAreProjectedToUrlAndFilename() {
        val photo = savedRecord().copy().photos?.single()

        assertEquals("https://example.com/one.png", photo?.url)
        assertEquals("one.png", photo?.filename)
        assertNull(photo?.id, "create rejects a server attachment id (INVALID_ATTACHMENT_OBJECT)")
        assertNull(photo?.size)
        assertNull(photo?.type)
        assertNull(photo?.thumbnails)
    }

    @Test
    fun projectedAttachmentsSerializeToExactlyUrlAndFilename() {
        // The wire check: nulls are dropped on encode, so the create body carries the
        // two-key object Airtable's whitelist accepts and nothing else.
        val encoded = JsonObject(savedRecord().copy().toCreateFields())["fldPhotos"]!!.jsonArray.single().jsonObject

        assertEquals(setOf("url", "filename"), encoded.keys)
    }

    @Test
    fun computedAttachmentShapedCellsKeepTheirFullMetadata() {
        // A lookup can hold the same shape as an attachment cell, but it is never
        // written back — stripping its metadata would lose fidelity for nothing.
        val lookup = savedRecord().copy().lookupPhotos?.single()

        assertEquals("attLook000000001", lookup?.id)
        assertEquals(1234L, lookup?.size)
        assertEquals("image/png", lookup?.type)
        assertEquals("https://example.com/small-look.png", lookup?.thumbnails?.small?.url)
    }

    // endregion

    // region no shared mutable state

    @Test
    fun listContainersAreRebuiltNotAliased() {
        val source = savedRecord()
        val copied = source.copy()

        assertNotSame(source.tags, copied.tags, "a shared list would let a mutation of one be felt by the other")
        assertNotSame(source.photos, copied.photos)
        assertNotSame(source.links, copied.links)
        assertNotSame(source.lookupPhotos, copied.lookupPhotos)
    }

    @Test
    fun mutatingTheSourcesOwnListDoesNotReachTheCopy() {
        // The properties are typed `List<T>`, but kotlinx decodes into an ArrayList and
        // callers can hand in a MutableList, so the underlying container really is mutable.
        val tags = mutableListOf("a", "b")
        val source = savedRecord().apply { this.tags = tags }
        val copied = source.copy()

        tags.add("c")

        assertEquals(listOf("a", "b"), copied.tags)
        assertEquals(listOf("a", "b", "c"), source.tags)
    }

    @Test
    fun mutatingTheCopyLeavesTheSourceAlone() {
        val source = savedRecord()
        val copied = source.copy()

        copied.name = "renamed"
        copied.tags = listOf("z")
        copied.links = listOf("recSomethingElse1")
        copied.photos = emptyList()

        assertEquals("original", source.name)
        assertEquals(listOf("a", "b"), source.tags)
        assertEquals(listOf("recLinked00000001", "recLinked00000002"), source.links)
        assertEquals(1, source.photos?.size)
    }

    @Test
    fun copyLeavesTheSourceCompletelyUntouched() {
        val client = AirtableClient(baseId = "appX", apiKey = "key")
        client.use {
            val source = savedRecord(client)
            val before = JsonObject(source.toRecord())

            source.copy()

            assertEquals("recSource00000001", source.id)
            assertEquals(Instant.parse("2026-01-01T00:00:00Z"), source.createdTime)
            assertSame(client, source.attachedClient)
            assertTrue(source.dirtyFields().isEmpty(), "copy() must not disturb the source's snapshot")
            assertEquals(before, JsonObject(source.toRecord()))
            // Notably the source's own attachment keeps its server metadata: the
            // projection happens on the way OUT, into the copy.
            assertEquals("attOne0000000001", source.photos?.single()?.id)
        }
    }

    // endregion

    // region I/O

    @Test
    fun copyPerformsNoIO() =
        runTest {
            // Nothing in copy() may touch the transport — that is the entire difference
            // from the table's duplicate(), which re-reads the source first.
            val engine = MockEngine { error("copy() must not make any HTTP request") }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            client.use {
                savedRecord(client).copy().copy()
                assertTrue(engine.requestHistory.isEmpty())
            }
        }

    @Test
    fun creatingACopySendsAPostWithTheProjectedWritableSet() =
        runTest {
            val bodies = mutableListOf<JsonObject>()
            val methods = mutableListOf<HttpMethod>()
            val engine =
                MockEngine { request ->
                    methods.add(request.method)
                    bodies.add(AirtableJson.instance.parseToJsonElement(request.body.toByteArray().decodeToString()).jsonObject)
                    respond(
                        content = """{"records": [{"id": "recNew00000000001", "createdTime": "2026-02-02T00:00:00.000Z", "fields": {"fldName": "copied"}}]}""",
                        status = HttpStatusCode.OK,
                        headers = headersOf(HttpHeaders.ContentType, "application/json"),
                    )
                }
            val client = AirtableClient(baseId = "appX", apiKey = "key", httpClient = HttpClient(engine))
            client.use {
                val table = OrmTable(tableId = "tblStub", serializer = CopyStubModel.serializer(), client = client)
                val copied = savedRecord(client).copy().apply { name = "copied" }

                val created = table.create(copied)

                assertEquals(HttpMethod.Post, methods.single(), "a carried id would have made this a PATCH of the source row")
                val fields =
                    bodies
                        .single()["records"]!!
                        .jsonArray
                        .single()
                        .jsonObject["fields"]!!
                        .jsonObject
                assertEquals(setOf("fldName", "fldTags", "fldPhotos", "fldLinks"), fields.keys)
                assertEquals(
                    setOf("url", "filename"),
                    fields["fldPhotos"]!!
                        .jsonArray
                        .single()
                        .jsonObject.keys,
                )
                assertEquals("recNew00000000001", created.id, "the created record is a NEW row")
            }
        }

    // endregion
}
