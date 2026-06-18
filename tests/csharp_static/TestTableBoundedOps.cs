using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS11.1 — bounded multi-id get + empty-diff update partition + offset pagination (parity with the
/// Java/Kotlin TestTableBoundedOps). The observable contracts that must survive the bounded fan-out:
/// each id's payload returns in its requested slot; clean models are never PATCHed and return as-is;
/// the offset loop pages until exhausted carrying the original query.
/// </summary>
public class TestTableBoundedOps
{
    /// <summary>Minimal hand-written model mirroring what the generator emits.</summary>
    private sealed class BoundedOpsStubModel : AirtableModel
    {
        public override string TableId => "tblStub";

        [JsonPropertyName("fldName")]
        public string? Name { get; set; }

        protected override IReadOnlyDictionary<string, JsonNode?> CollectWritableFields() =>
            new Dictionary<string, JsonNode?> { ["fldName"] = AirtableRuntime.V(Name) };

        protected override IReadOnlyDictionary<string, JsonNode?> CollectComputedFields() =>
            new Dictionary<string, JsonNode?>();
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

    /// <summary>Echoes the record id from the request URL back as the payload.</summary>
    private static FakeTransport EchoTransport() =>
        new(
            (request, _) =>
            {
                var path = request.RequestUri!.AbsolutePath;
                var recordId = path[(path.LastIndexOf('/') + 1)..];
                return FakeTransport.Canned.Ok(
                    $"{{\"id\": \"{recordId}\", \"fields\": {{\"fldName\": \"name-{recordId}\"}}}}"
                );
            }
        );

    // A fixed non-sequential permutation of rec01..rec12 — order must round-trip regardless of input order.
    private static List<string> ShuffledIds() =>
        new()
        {
            "rec07",
            "rec02",
            "rec11",
            "rec05",
            "rec01",
            "rec09",
            "rec12",
            "rec03",
            "rec08",
            "rec04",
            "rec10",
            "rec06",
        };

    // ---- multi-get order ----

    [Fact]
    public async Task DictTableMultiGetPreservesCallerOrder()
    {
        var ids = ShuffledIds();
        var table = new DictTable(
            "tblStub",
            new Dictionary<string, string>(),
            ClientWith(EchoTransport())
        );
        var records = await table.GetAsync(ids);
        Assert.Equal(ids, records.Select(r => r.Id).ToList());
    }

    [Fact]
    public async Task OrmTableMultiGetPreservesCallerOrder()
    {
        var ids = ShuffledIds();
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(EchoTransport()));
        var models = await table.GetAsync(ids);
        Assert.Equal(ids, models.Select(m => m.Id!).ToList());
        Assert.Equal(ids.Select(id => $"name-{id}").ToList(), models.Select(m => m.Name!).ToList());
    }

    [Fact]
    public async Task MultiGetBoundsInFlightRequestsToMaxConcurrentGets()
    {
        // The fan-out's whole reason for existing is to cap concurrency below Airtable's rate
        // limit. With per-request latency the windows of 4 overlap, so the high-water mark proves
        // both that requests *do* run concurrently (> 1) and that the cap is never breached.
        var ids = Enumerable.Range(1, 12).Select(i => $"rec{i:D2}").ToList();
        var transport = new FakeTransport(
            (request, _) =>
            {
                var path = request.RequestUri!.AbsolutePath;
                var recordId = path[(path.LastIndexOf('/') + 1)..];
                return FakeTransport.Canned.Ok($"{{\"id\": \"{recordId}\", \"fields\": {{}}}}");
            },
            entryDelayMs: 25
        );
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(transport));

        var models = await table.GetAsync(ids);

        Assert.Equal(ids, models.Select(m => m.Id!).ToList());
        Assert.True(
            transport.MaxConcurrent <= OrmTable<BoundedOpsStubModel>.MaxConcurrentGets,
            $"in-flight {transport.MaxConcurrent} exceeded cap {OrmTable<BoundedOpsStubModel>.MaxConcurrentGets}"
        );
        Assert.True(
            transport.MaxConcurrent > 1,
            "expected requests to overlap, but they serialized"
        );
    }

    [Fact]
    public async Task MultiGetEmptyInputMakesNoRequests()
    {
        var transport = EchoTransport();
        var table = new DictTable(
            "tblStub",
            new Dictionary<string, string>(),
            ClientWith(transport)
        );
        var records = await table.GetAsync(new List<string>());
        Assert.Empty(records);
        Assert.Empty(transport.RequestHistory);
    }

    // ---- update partition ----

    private static BoundedOpsStubModel CleanModel(string recordId)
    {
        var model = new BoundedOpsStubModel { Name = "server-" + recordId, Id = recordId };
        model.TakeSnapshot();
        return model;
    }

    private static FakeTransport PatchRejectingTransport() =>
        new(
            (request, _) =>
                request.Method == HttpMethod.Patch
                    ? new FakeTransport.Canned(500, "{\"error\": \"PATCH must not happen\"}")
                    : FakeTransport.Canned.Ok("{\"records\": []}")
        );

    [Fact]
    public async Task AllCleanModelsUpdateWithoutAnyRequest()
    {
        var transport = PatchRejectingTransport();
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(transport));
        var models = new List<BoundedOpsStubModel>
        {
            CleanModel("rec01"),
            CleanModel("rec02"),
            CleanModel("rec03"),
        };

        var results = await table.UpdateAsync(models);

        Assert.Empty(transport.RequestHistory);
        Assert.Equal(3, results.Count);
        for (var i = 0; i < models.Count; i++)
            Assert.Same(models[i], results[i]); // clean models come back as the same instance, in position
    }

    [Fact]
    public async Task MixedListPatchesOnlyTheDirtyModelAndPreservesOrder()
    {
        var transport = new FakeTransport(
            (_, _) =>
                FakeTransport.Canned.Ok(
                    "{\"records\": [{\"id\": \"rec02\", \"fields\": {\"fldName\": \"renamed\"}}]}"
                )
        );
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(transport));

        var clean1 = CleanModel("rec01");
        var dirty = CleanModel("rec02");
        dirty.Name = "renamed";
        var clean2 = CleanModel("rec03");

        var results = await table.UpdateAsync(
            new List<BoundedOpsStubModel> { clean1, dirty, clean2 }
        );

        Assert.Single(transport.RequestHistory);
        var request = transport.RequestHistory[0];
        Assert.Equal(HttpMethod.Patch, request.Method);
        Assert.Contains("rec02", request.Body!);
        Assert.DoesNotContain("rec01", request.Body!);
        Assert.DoesNotContain("rec03", request.Body!);

        Assert.Equal(3, results.Count);
        Assert.Same(clean1, results[0]);
        Assert.Equal("rec02", results[1].Id);
        Assert.Equal("renamed", results[1].Name);
        Assert.Same(clean2, results[2]);
    }

    [Fact]
    public async Task SingleCleanModelUpdateIsANoOp()
    {
        var transport = PatchRejectingTransport();
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(transport));
        var model = CleanModel("rec01");

        var result = await table.UpdateAsync(model);

        Assert.Empty(transport.RequestHistory);
        Assert.Same(model, result);
    }

    // ---- pagination ----

    private static FakeTransport PagedTransport() =>
        new(
            (_, callIndex) =>
                callIndex == 0
                    ? FakeTransport.Canned.Ok(
                        "{\"records\": [{\"id\": \"rec01\", \"fields\": {\"fldName\": \"a\"}},"
                            + " {\"id\": \"rec02\", \"fields\": {\"fldName\": \"b\"}}],"
                            + " \"offset\": \"tok-page2\"}"
                    )
                    : FakeTransport.Canned.Ok(
                        "{\"records\": [{\"id\": \"rec03\", \"fields\": {\"fldName\": \"c\"}}]}"
                    )
        );

    [Fact]
    public async Task OrmGetFollowsOffsetMergesPagesInOrderAndTerminates()
    {
        var transport = PagedTransport();
        var table = new OrmTable<BoundedOpsStubModel>("tblStub", ClientWith(transport));

        var models = await table.GetAsync(new AirtableQuery().WithFormula("{fldName}!=BLANK()"));

        Assert.Equal(
            new List<string> { "rec01", "rec02", "rec03" },
            models.Select(m => m.Id!).ToList()
        );
        Assert.Equal(2, transport.RequestHistory.Count);
        var page2 = transport.RequestHistory[1].Url;
        Assert.Contains("offset=tok-page2", page2);
        Assert.Contains("filterByFormula", page2);
    }

    [Fact]
    public async Task DictGetFollowsOffsetAndTerminates()
    {
        var transport = PagedTransport();
        var table = new DictTable(
            "tblStub",
            new Dictionary<string, string>(),
            ClientWith(transport)
        );

        var records = await table.GetAsync(new AirtableQuery());

        Assert.Equal(
            new List<string> { "rec01", "rec02", "rec03" },
            records.Select(r => r.Id).ToList()
        );
        Assert.Equal(2, transport.RequestHistory.Count);
    }
}
