using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// myairtable-hbph — the per-request <c>typecast</c> flag on create/update/upsert. Airtable coerces
/// string inputs to the cell type only when the write body carries <c>"typecast": true</c>; the key
/// MUST be absent by default so existing behavior is unchanged. These tests drive the real public
/// methods through the offline <see cref="FakeTransport"/>, capture the request body, and assert the
/// flag is present iff opted in.
/// </summary>
public class TestTypecastOption
{
    private sealed class StubModel : AirtableModel
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

    /// <summary>Echoes back a single created/updated record so decoding succeeds.</summary>
    private static FakeTransport EchoWriteTransport() =>
        new(
            (_, _) =>
                FakeTransport.Canned.Ok(
                    "{\"records\": [{\"id\": \"rec01\", \"fields\": {\"fldName\": \"x\"}}]}"
                )
        );

    private static JsonObject ParsedBody(FakeTransport transport)
    {
        Assert.Single(transport.RequestHistory);
        var body = transport.RequestHistory[0].Body;
        Assert.NotNull(body);
        return Assert.IsType<JsonObject>(JsonNode.Parse(body!));
    }

    private static StubModel Dirty(string id)
    {
        var model = new StubModel { Name = "before", Id = id };
        model.TakeSnapshot();
        model.Name = "after";
        return model;
    }

    // ---- OrmTable.Create ----

    [Fact]
    public async Task OrmCreateOmitsTypecastByDefault()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.CreateAsync(new StubModel { Name = "n" });

        Assert.False(ParsedBody(transport).ContainsKey("typecast"));
    }

    [Fact]
    public async Task OrmCreateEmitsTypecastWhenSet()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.CreateAsync(new StubModel { Name = "n" }, typecast: true);

        Assert.True(ParsedBody(transport)["typecast"]!.GetValue<bool>());
    }

    // ---- OrmTable.Update ----

    [Fact]
    public async Task OrmUpdateOmitsTypecastByDefault()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.UpdateAsync(Dirty("rec01"));

        Assert.False(ParsedBody(transport).ContainsKey("typecast"));
    }

    [Fact]
    public async Task OrmUpdateEmitsTypecastWhenSet()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.UpdateAsync(Dirty("rec01"), typecast: true);

        Assert.True(ParsedBody(transport)["typecast"]!.GetValue<bool>());
    }

    // ---- OrmTable.Upsert ----

    [Fact]
    public async Task OrmUpsertOmitsTypecastByDefault()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.UpsertAsync(new StubModel { Name = "n" }, new[] { "fldName" });

        Assert.False(ParsedBody(transport).ContainsKey("typecast"));
    }

    [Fact]
    public async Task OrmUpsertEmitsTypecastWhenSet()
    {
        var transport = EchoWriteTransport();
        var table = new OrmTable<StubModel>("tblStub", ClientWith(transport));

        await table.UpsertAsync(new StubModel { Name = "n" }, new[] { "fldName" }, typecast: true);

        Assert.True(ParsedBody(transport)["typecast"]!.GetValue<bool>());
    }

    // ---- DictTable.Create / Update ----

    private static DictTable DictWith(FakeTransport transport) =>
        new("tblStub", new Dictionary<string, string>(), ClientWith(transport));

    [Fact]
    public async Task DictCreateOmitsTypecastByDefault()
    {
        var transport = EchoWriteTransport();
        var table = DictWith(transport);

        await table.CreateAsync(
            new Fields(new Dictionary<string, JsonNode?> { ["fldName"] = "n" })
        );

        Assert.False(ParsedBody(transport).ContainsKey("typecast"));
    }

    [Fact]
    public async Task DictCreateEmitsTypecastWhenSet()
    {
        var transport = EchoWriteTransport();
        var table = DictWith(transport);

        await table.CreateAsync(
            new Fields(new Dictionary<string, JsonNode?> { ["fldName"] = "n" }),
            typecast: true
        );

        Assert.True(ParsedBody(transport)["typecast"]!.GetValue<bool>());
    }

    [Fact]
    public async Task DictUpdateOmitsTypecastByDefault()
    {
        var transport = EchoWriteTransport();
        var table = DictWith(transport);

        await table.UpdateAsync(
            "rec01",
            new Fields(new Dictionary<string, JsonNode?> { ["fldName"] = "n" })
        );

        Assert.False(ParsedBody(transport).ContainsKey("typecast"));
    }

    [Fact]
    public async Task DictUpdateEmitsTypecastWhenSet()
    {
        var transport = EchoWriteTransport();
        var table = DictWith(transport);

        await table.UpdateAsync(
            "rec01",
            new Fields(new Dictionary<string, JsonNode?> { ["fldName"] = "n" }),
            typecast: true
        );

        Assert.True(ParsedBody(transport)["typecast"]!.GetValue<bool>());
    }
}
