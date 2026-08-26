using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// myairtable-6q37.9 — the local <c>Copy()</c> verb. <c>record.Copy()</c> returns a detached,
/// unsaved model you mutate and hand to the table's <c>CreateAsync</c>; it performs no I/O, which
/// makes it fully hermetically testable (unlike <c>DuplicateAsync</c>).
///
/// <para><see cref="CopyStubModel"/> is a stand-in built to the EXACT shape csharp.py emits —
/// public setters on writable properties, <c>[JsonInclude]</c> + <c>private set</c> on computed
/// ones, the two <c>Collect…</c> overrides, and a <c>Copy()</c> whose body is the generated
/// initializer verbatim. The generated code is not compiled here (the .csproj compiles only the
/// static runtime), so this file is also what pins the emitted call shapes: if an overload of
/// <c>DetachForCopy</c> stopped resolving, this file would stop compiling.</para>
/// </summary>
public class TestCopyPayload
{
    private sealed class CopyStubModel : AirtableModel
    {
        public override string TableId => "tblCopy";

        [JsonPropertyName("fldName")]
        public string? Name { get; set; }

        [JsonPropertyName("fldTags")]
        public List<string>? Tags { get; set; }

        [JsonPropertyName("fldPhotos")]
        public List<AirtableAttachment>? Photos { get; set; }

        [JsonPropertyName("fldLinks")]
        public List<string>? Links { get; set; }

        [JsonPropertyName("fldRaw")]
        public JsonNode? Raw { get; set; }

        [JsonPropertyName("fldWhen")]
        public DateTimeOffset? When { get; set; }

        [JsonPropertyName("fldFormula")]
        [JsonInclude]
        public MaybeSpecialOrError<double>? Formula { get; private set; }

        /// <summary>A computed lookup OF AN ATTACHMENT FIELD — same cell shape, read-only.</summary>
        [JsonPropertyName("fldLookup")]
        [JsonInclude]
        public VecOrValue<MaybeSpecialOrError<JsonNode>>? Lookup { get; private set; }

        [JsonPropertyName("fldRawLookup")]
        [JsonInclude]
        public VecOrValue<JsonNode>? RawLookup { get; private set; }

        protected override IReadOnlyDictionary<string, JsonNode?> CollectWritableFields() =>
            new Dictionary<string, JsonNode?>
            {
                ["fldName"] = AirtableRuntime.V(Name),
                ["fldTags"] = AirtableRuntime.V(Tags),
                ["fldPhotos"] = AirtableRuntime.V(Photos),
                ["fldLinks"] = AirtableRuntime.V(Links),
                ["fldRaw"] = AirtableRuntime.V(Raw),
                ["fldWhen"] = AirtableRuntime.V(When),
            };

        protected override IReadOnlyDictionary<string, JsonNode?> CollectComputedFields() =>
            new Dictionary<string, JsonNode?>
            {
                ["fldFormula"] = AirtableRuntime.V(Formula),
                ["fldLookup"] = AirtableRuntime.V(Lookup),
                ["fldRawLookup"] = AirtableRuntime.V(RawLookup),
            };

        /// <summary>Generated body, verbatim. Id / CreatedTime are deliberately never named.</summary>
        public CopyStubModel Copy() =>
            new()
            {
                AttachedClient = AttachedClient,
                Name = Name,
                Tags = DetachForCopy(Tags),
                Photos = ProjectAttachmentsForCopy(Photos),
                Links = DetachForCopy(Links),
                Raw = DetachForCopy(Raw),
                When = When,
                Formula = DetachForCopy(Formula),
                Lookup = DetachForCopy(Lookup),
                RawLookup = DetachForCopy(RawLookup),
            };

        /// <summary>
        /// Test-only seeding of the decode-only properties. In production STJ writes them through
        /// the private setter on decode; the private setter is what <c>Copy()</c> uses too, and
        /// both are legal only from inside the class — which is exactly why the generator emits
        /// <c>Copy()</c> into the model rather than putting it on the base.
        /// </summary>
        public CopyStubModel Seed(
            MaybeSpecialOrError<double>? formula,
            VecOrValue<MaybeSpecialOrError<JsonNode>>? lookup,
            VecOrValue<JsonNode>? rawLookup
        )
        {
            Formula = formula;
            Lookup = lookup;
            RawLookup = rawLookup;
            return this;
        }
    }

    /// <summary>An attachment exactly as Airtable returns it — create rejects all of this but the URL.</summary>
    private static AirtableAttachment ServerAttachment() =>
        new()
        {
            Id = "attServerSide0001",
            Url = "https://example.com/a.png",
            Filename = "a.png",
            Size = 1234,
            Type = "image/png",
            Thumbnails = new AirtableThumbnails(
                new AirtableThumbnail("https://example.com/s.png", 10, 10),
                null,
                null
            ),
        };

    private static JsonObject ServerAttachmentNode() =>
        new()
        {
            ["id"] = "attLookupSide0001",
            ["url"] = "https://example.com/b.png",
            ["filename"] = "b.png",
            ["size"] = 99,
            ["type"] = "image/png",
        };

    /// <summary>A table-produced model: server identity, a client attached, a snapshot taken.</summary>
    private static CopyStubModel Source(AirtableClient? client = null)
    {
        var model = new CopyStubModel
        {
            Id = "recSOURCE0001",
            CreatedTime = DateTimeOffset.Parse("2024-01-02T03:04:05Z"),
            AttachedClient = client ?? new AirtableClient("appX", "key"),
            Name = "original",
            Tags = new List<string> { "a", "b" },
            Photos = new List<AirtableAttachment> { ServerAttachment() },
            Links = new List<string> { "recOTHER0001" },
            Raw = new JsonObject { ["nested"] = new JsonObject { ["k"] = "v" } },
            When = DateTimeOffset.Parse("2024-05-06T07:08:09Z"),
        }.Seed(
            new MaybeSpecialOrError<double>.Value(42.0),
            new VecOrValue<MaybeSpecialOrError<JsonNode>>.Multiple(
                new List<MaybeSpecialOrError<JsonNode>?>
                {
                    new MaybeSpecialOrError<JsonNode>.Value(ServerAttachmentNode()),
                }
            ),
            new VecOrValue<JsonNode>.Single(new JsonObject { ["deep"] = "value" })
        );
        model.TakeSnapshot();
        return model;
    }

    // ---- the detach ---------------------------------------------------------

    [Fact]
    public void CopyCarriesNoRecordIdentity()
    {
        var copy = Source().Copy();

        Assert.Null(copy.Id);
        Assert.Null(copy.CreatedTime);
        // IsNew is derived from Id, so a null Id IS the "unsaved" state — there is no flag to reset.
        Assert.True(copy.IsNew);
        Assert.Throws<AirtableException.ApiError>(() => copy.RequireId());
    }

    [Fact]
    public void CopyKeepsTheAttachedClient()
    {
        var source = Source();
        var copy = source.Copy();

        // Contract item 4: the client is kept so `table.CreateAsync(record.Copy())` — and the
        // model's own fluent CRUD after that insert — work without re-threading a client.
        Assert.Same(source.AttachedClient, copy.AttachedClient);
        Assert.Same(source.AttachedClient, copy.RequireAttachedClient());
    }

    [Fact]
    public void CopyIsFullyDirtyWhileTheSourceStaysClean()
    {
        var source = Source();
        var copy = source.Copy();

        // The trap: a copy that carried the source's snapshot would diff to nothing, and the
        // insert would POST {"fields":{}} — a blank record, silently.
        Assert.Empty(source.DirtyFields());
        var dirty = copy.DirtyFields();
        foreach (
            var id in new[] { "fldName", "fldTags", "fldPhotos", "fldLinks", "fldRaw", "fldWhen" }
        )
            Assert.True(dirty.ContainsKey(id), $"{id} should be dirty on an unsnapshotted copy");
    }

    [Fact]
    public void CopyIsANewInstanceOfTheSameType()
    {
        var source = Source();
        CopyStubModel copy = source.Copy();

        Assert.NotSame(source, copy);
        Assert.Equal(source.TableId, copy.TableId);
    }

    // ---- computed values ----------------------------------------------------

    [Fact]
    public void ComputedValuesAreCarriedSoTheCopyReadsLikeItsSource()
    {
        var source = Source();
        var copy = source.Copy();

        Assert.Equal(42.0, Assert.IsType<MaybeSpecialOrError<double>.Value>(copy.Formula).Content);
        Assert.NotNull(copy.Lookup);
        Assert.NotNull(copy.RawLookup);
        Assert.Equal(
            AirtableRuntime.V(source.Lookup)!.ToJsonString(),
            AirtableRuntime.V(copy.Lookup)!.ToJsonString()
        );
    }

    [Fact]
    public void ComputedValuesNeverReachTheCreatePayload()
    {
        var copy = Source().Copy();
        var fields = copy.ToCreateFields();

        // ToCreateFields is built from CollectWritableFields alone, and it is the sole input to
        // OrmTable.CreateAsync — which is what makes carrying computed values safe on the wire.
        Assert.True(fields.ContainsKey("fldName"));
        foreach (var id in new[] { "fldFormula", "fldLookup", "fldRawLookup" })
            Assert.False(fields.ContainsKey(id), $"{id} is computed and must not be sent");
        // …while still being readable off the model.
        Assert.NotNull(copy.Formula);
    }

    [Fact]
    public void SpecialAndErrorComputedValuesSurviveTheCopy()
    {
        var source = new CopyStubModel().Seed(
            new MaybeSpecialOrError<double>.Special(new SpecialNumber("NaN")),
            new VecOrValue<MaybeSpecialOrError<JsonNode>>.Single(
                new MaybeSpecialOrError<JsonNode>.Error(new ErrorValue("#ERROR"))
            ),
            null
        );
        var copy = source.Copy();

        Assert.Equal(
            "NaN",
            Assert.IsType<MaybeSpecialOrError<double>.Special>(copy.Formula).Number.SpecialValue
        );
        var single = Assert.IsType<VecOrValue<MaybeSpecialOrError<JsonNode>>.Single>(copy.Lookup);
        Assert.Equal(
            "#ERROR",
            Assert.IsType<MaybeSpecialOrError<JsonNode>.Error>(single.Value).Err.Error
        );
        Assert.Null(copy.RawLookup);
    }

    // ---- attachments --------------------------------------------------------

    [Fact]
    public void WritableAttachmentsAreProjectedToUrlAndFilename()
    {
        var copy = Source().Copy();

        var attachment = Assert.Single(copy.Photos!);
        Assert.Equal("https://example.com/a.png", attachment.Url);
        Assert.Equal("a.png", attachment.Filename);
        // Airtable answers INVALID_ATTACHMENT_OBJECT to an id echoed back on create.
        Assert.Null(attachment.Id);
        Assert.Null(attachment.Size);
        Assert.Null(attachment.Type);
        Assert.Null(attachment.Thumbnails);
    }

    [Fact]
    public void ProjectedAttachmentsSerializeToExactlyUrlAndFilename()
    {
        var copy = Source().Copy();

        var cell = Assert.IsType<JsonArray>(copy.ToCreateFields()["fldPhotos"]);
        var entry = Assert.IsType<JsonObject>(Assert.Single(cell));
        var keys = new List<string>();
        foreach (var pair in entry)
            keys.Add(pair.Key);
        Assert.Equal(new List<string> { "url", "filename" }, keys);
    }

    [Fact]
    public void CallerBuiltAttachmentsSurviveTheProjection()
    {
        var source = new CopyStubModel
        {
            Photos = new List<AirtableAttachment> { new() { Url = "https://example.com/new.png" } },
        };
        var attachment = Assert.Single(source.Copy().Photos!);

        Assert.Equal("https://example.com/new.png", attachment.Url);
        Assert.Null(attachment.Filename);
    }

    [Fact]
    public void ComputedAttachmentShapedCellsKeepTheirMetadata()
    {
        var copy = Source().Copy();

        // A lookup of an attachment field holds the identical shape but is never written back,
        // so stripping its read-only metadata would lose fidelity for nothing.
        var multiple = Assert.IsType<VecOrValue<MaybeSpecialOrError<JsonNode>>.Multiple>(
            copy.Lookup
        );
        var value = Assert.IsType<MaybeSpecialOrError<JsonNode>.Value>(
            Assert.Single(multiple.Values)
        );
        var entry = Assert.IsType<JsonObject>(value.Content);
        Assert.Equal("attLookupSide0001", entry["id"]!.GetValue<string>());
        Assert.Equal(99, entry["size"]!.GetValue<int>());
    }

    // ---- no shared mutable state -------------------------------------------

    [Fact]
    public void ListCellsAreRebuiltNotAliased()
    {
        var source = Source();
        var copy = source.Copy();

        Assert.NotSame(source.Tags, copy.Tags);
        Assert.NotSame(source.Photos, copy.Photos);
        Assert.NotSame(source.Links, copy.Links);

        copy.Tags!.Add("c");
        copy.Links!.Clear();
        copy.Photos!.Add(new AirtableAttachment { Url = "https://example.com/extra.png" });

        Assert.Equal(new List<string> { "a", "b" }, source.Tags);
        Assert.Equal(new List<string> { "recOTHER0001" }, source.Links);
        Assert.Single(source.Photos!);
    }

    [Fact]
    public void JsonNodeCellsAreDeepCloned()
    {
        var source = Source();
        var copy = source.Copy();

        Assert.NotSame(source.Raw, copy.Raw);
        copy.Raw!["nested"]!["k"] = "mutated";
        copy.Raw["added"] = true;

        Assert.Equal("v", source.Raw!["nested"]!["k"]!.GetValue<string>());
        Assert.Null(source.Raw["added"]);
    }

    [Fact]
    public void ComputedWrapperContentsAreDeepClonedToo()
    {
        var source = Source();
        var copy = source.Copy();

        // VecOrValue/MaybeSpecialOrError are immutable records, but Multiple wraps a mutable list
        // and a lookup entry bottoms out in an editable JsonNode.
        var sourceEntries = Assert.IsType<VecOrValue<MaybeSpecialOrError<JsonNode>>.Multiple>(
            source.Lookup
        );
        var copyEntries = Assert.IsType<VecOrValue<MaybeSpecialOrError<JsonNode>>.Multiple>(
            copy.Lookup
        );
        Assert.NotSame(sourceEntries.Values, copyEntries.Values);

        var copyNode = Assert
            .IsType<MaybeSpecialOrError<JsonNode>.Value>(Assert.Single(copyEntries.Values))
            .Content;
        var sourceNode = Assert
            .IsType<MaybeSpecialOrError<JsonNode>.Value>(Assert.Single(sourceEntries.Values))
            .Content;
        Assert.NotSame(sourceNode, copyNode);

        copyNode!["url"] = "https://example.com/mutated.png";
        Assert.Equal("https://example.com/b.png", sourceNode!["url"]!.GetValue<string>());
    }

    [Fact]
    public void SingleShapedLookupContentIsDeepClonedToo()
    {
        var source = Source();
        var copy = source.Copy();

        var sourceSingle = Assert.IsType<VecOrValue<JsonNode>.Single>(source.RawLookup);
        var copySingle = Assert.IsType<VecOrValue<JsonNode>.Single>(copy.RawLookup);
        Assert.NotSame(sourceSingle.Value, copySingle.Value);

        copySingle.Value!["deep"] = "mutated";
        Assert.Equal("value", sourceSingle.Value!["deep"]!.GetValue<string>());
    }

    [Fact]
    public void MutatingTheSourceAfterCopyingDoesNotReachTheCopy()
    {
        var source = Source();
        var copy = source.Copy();

        source.Tags!.Add("c");
        source.Raw!["nested"]!["k"] = "mutated";
        source.Name = "renamed";

        Assert.Equal(new List<string> { "a", "b" }, copy.Tags);
        Assert.Equal("v", copy.Raw!["nested"]!["k"]!.GetValue<string>());
        Assert.Equal("original", copy.Name);
    }

    [Fact]
    public void TheSourceIsLeftCompletelyUntouched()
    {
        var source = Source();
        var before = Fingerprint(source);

        var copy = source.Copy();
        copy.Name = "mutated";
        copy.Tags!.Add("c");
        copy.Photos!.Clear();

        Assert.Equal("recSOURCE0001", source.Id);
        Assert.Equal(DateTimeOffset.Parse("2024-01-02T03:04:05Z"), source.CreatedTime);
        Assert.Empty(source.DirtyFields());
        Assert.Equal(before, Fingerprint(source));
    }

    // ---- empty / null cells -------------------------------------------------

    [Fact]
    public void CopyingAnEmptyModelYieldsNullCellsNotEmptyContainers()
    {
        var copy = new CopyStubModel().Copy();

        Assert.Null(copy.Name);
        Assert.Null(copy.Tags);
        Assert.Null(copy.Photos);
        Assert.Null(copy.Raw);
        Assert.Null(copy.Formula);
        Assert.Null(copy.Lookup);
        Assert.Null(copy.AttachedClient);
        // A null cell is not "changed", so nothing is dirty and nothing is sent.
        Assert.Empty(copy.DirtyFields());
        Assert.Empty(copy.ToCreateFields());
    }

    // ---- zero I/O -----------------------------------------------------------

    [Fact]
    public void CopyIssuesNoRequestAtAll()
    {
        var transport = new FakeTransport(
            (_, _) => throw new InvalidOperationException("Copy() must not perform I/O")
        );
        var source = Source(ClientWith(transport));

        var copy = source.Copy();

        Assert.Empty(transport.RequestHistory);
        Assert.Equal("original", copy.Name);
    }

    [Fact]
    public async Task CreatingACopyPostsTheProjectedWritableSet()
    {
        var transport = new FakeTransport(
            (_, _) =>
                FakeTransport.Canned.Ok(
                    "{\"records\": [{\"id\": \"recNEW0001\", \"fields\": {\"fldName\": \"original\"}}]}"
                )
        );
        var client = ClientWith(transport);
        var table = new OrmTable<CopyStubModel>("tblCopy", client);

        var created = await table.CreateAsync(Source(client).Copy());

        Assert.Equal("recNEW0001", created.Id);
        var request = Assert.Single(transport.RequestHistory);
        var body = Assert.IsType<JsonObject>(JsonNode.Parse(request.Body!));
        var fields = Assert.IsType<JsonObject>(
            Assert.IsType<JsonArray>(body["records"])[0]!["fields"]
        );
        // Writable only — nothing computed, and no record id anywhere in the body.
        Assert.Equal("original", fields["fldName"]!.GetValue<string>());
        Assert.Null(fields["fldFormula"]);
        Assert.Null(fields["fldLookup"]);
        Assert.DoesNotContain("recSOURCE0001", request.Body!);
        // The attachment went out projected: create rejects a server-returned attachment object.
        var attachment = Assert.IsType<JsonObject>(
            Assert.IsType<JsonArray>(fields["fldPhotos"])[0]
        );
        Assert.Equal("https://example.com/a.png", attachment["url"]!.GetValue<string>());
        Assert.Null(attachment["id"]);
    }

    /// <summary>Every cell of a model as one comparable string (ToRecord's nodes stay parented).</summary>
    private static string Fingerprint(AirtableModel model)
    {
        var parts = new List<string>();
        foreach (var (id, value) in model.ToRecord())
            parts.Add($"{id}={value?.ToJsonString()}");
        parts.Sort(StringComparer.Ordinal);
        return string.Join("|", parts);
    }

    private static AirtableClient ClientWith(FakeTransport transport) =>
        new(
            "appX",
            "key",
            transport,
            cacheSeconds: 0,
            baseRetryDelaySeconds: 0,
            retryJitterCapSeconds: 0
        );
}
