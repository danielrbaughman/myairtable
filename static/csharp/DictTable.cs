using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>
/// Untyped table facade: raw CRUD over <see cref="Fields"/> bags. Pairs with the generated
/// <c>OrmTable&lt;T&gt;</c> (F4) over the same <see cref="AirtableClient"/>. Mutating writes are
/// chunked into batches of <see cref="BatchSize"/> (the Airtable limit).
/// </summary>
public sealed class DictTable
{
    public const int BatchSize = 10;

    private readonly string _tableId;
    private readonly IReadOnlyDictionary<string, string> _nameToId;
    private readonly AirtableClient _client;

    public DictTable(
        string tableId,
        IReadOnlyDictionary<string, string> nameToId,
        AirtableClient client
    )
    {
        _tableId = tableId;
        _nameToId = nameToId;
        _client = client;
    }

    public string TableId => _tableId;

    public sealed record Record(string Id, DateTimeOffset CreatedTime, Fields Fields);

    public sealed record Update(string Id, Fields Fields);

    // ---- reads --------------------------------------------------------------

    public async Task<Record> GetAsync(string recordId, CancellationToken ct = default)
    {
        var payload = await _client.GetRecordAsync(_tableId, recordId, ct).ConfigureAwait(false);
        return ToRecord(Decode<RawEnvelope>(payload));
    }

    /// <summary>Fetch many records by id, preserving caller order.</summary>
    public async Task<List<Record>> GetAsync(
        IReadOnlyList<string> recordIds,
        CancellationToken ct = default
    )
    {
        var result = new List<Record>(recordIds.Count);
        foreach (var id in recordIds)
            result.Add(await GetAsync(id, ct).ConfigureAwait(false));
        return result;
    }

    public Task<List<Record>> GetAsync(CancellationToken ct = default) =>
        GetAsync(new AirtableQuery(), ct);

    public async Task<List<Record>> GetAsync(AirtableQuery query, CancellationToken ct = default)
    {
        var all = new List<Record>();
        string? offset = null;
        do
        {
            var payload = offset is null
                ? await _client.ListRecordsAsync(_tableId, query, ct).ConfigureAwait(false)
                : await FetchWithOffsetAsync(query, offset, ct).ConfigureAwait(false);
            var page = Decode<RawList>(payload);
            foreach (var raw in page.Records ?? new())
                all.Add(ToRecord(raw));
            offset = page.Offset;
        } while (!string.IsNullOrEmpty(offset));
        return all;
    }

    private Task<string> FetchWithOffsetAsync(
        AirtableQuery query,
        string offset,
        CancellationToken ct
    )
    {
        var pars = query.ToParameters();
        pars.Add(new("offset", offset));
        return _client.SendAsync(HttpMethod.Get, _client.TableUrl(_tableId, pars), null, ct);
    }

    // ---- creates ------------------------------------------------------------

    public async Task<Record> CreateAsync(Fields fields, CancellationToken ct = default) =>
        (await CreateAsync(new[] { fields }, ct).ConfigureAwait(false))[0];

    public async Task<List<Record>> CreateAsync(
        IReadOnlyList<Fields> fields,
        CancellationToken ct = default
    )
    {
        var created = new List<Record>(fields.Count);
        foreach (var batch in Chunk(fields))
        {
            var body = new JsonObject
            {
                ["records"] = new JsonArray(
                    batch
                        .Select(f => (JsonNode?)new JsonObject { ["fields"] = FieldsToJson(f) })
                        .ToArray()
                ),
                ["returnFieldsByFieldId"] = true,
            };
            var payload = await _client
                .CreateRecordsAsync(_tableId, body.ToJsonString(), ct)
                .ConfigureAwait(false);
            foreach (var raw in Decode<RawList>(payload).Records ?? new())
                created.Add(ToRecord(raw));
        }
        return created;
    }

    // ---- updates ------------------------------------------------------------

    public async Task<Record> UpdateAsync(
        string recordId,
        Fields fields,
        CancellationToken ct = default
    ) => (await UpdateAsync(new[] { new Update(recordId, fields) }, ct).ConfigureAwait(false))[0];

    public async Task<List<Record>> UpdateAsync(
        IReadOnlyList<Update> updates,
        CancellationToken ct = default
    )
    {
        var updated = new List<Record>(updates.Count);
        foreach (var batch in Chunk(updates))
        {
            var body = new JsonObject
            {
                ["records"] = new JsonArray(
                    batch
                        .Select(u =>
                            (JsonNode?)
                                new JsonObject
                                {
                                    ["id"] = u.Id,
                                    ["fields"] = FieldsToJson(u.Fields),
                                }
                        )
                        .ToArray()
                ),
                ["returnFieldsByFieldId"] = true,
            };
            var payload = await _client
                .UpdateRecordsAsync(_tableId, body.ToJsonString(), ct)
                .ConfigureAwait(false);
            foreach (var raw in Decode<RawList>(payload).Records ?? new())
                updated.Add(ToRecord(raw));
        }
        return updated;
    }

    // ---- deletes ------------------------------------------------------------

    public Task DeleteAsync(string recordId, CancellationToken ct = default) =>
        _client.DeleteRecordAsync(_tableId, recordId, ct);

    public async Task DeleteAsync(IReadOnlyList<string> recordIds, CancellationToken ct = default)
    {
        foreach (var batch in Chunk(recordIds))
            await _client.DeleteRecordsAsync(_tableId, batch.ToList(), ct).ConfigureAwait(false);
    }

    // ---- helpers ------------------------------------------------------------

    private Record ToRecord(RawEnvelope raw)
    {
        var storage = raw.Fields ?? new Dictionary<string, JsonNode?>();
        return new Record(raw.Id, raw.CreatedTime, new Fields(storage, _nameToId));
    }

    private static JsonObject FieldsToJson(Fields fields)
    {
        var obj = new JsonObject();
        foreach (var (id, value) in fields.ToMap())
            obj[id] = value?.DeepClone();
        return obj;
    }

    private static IEnumerable<IReadOnlyList<T>> Chunk<T>(IReadOnlyList<T> items)
    {
        for (var i = 0; i < items.Count; i += BatchSize)
            yield return items.Skip(i).Take(BatchSize).ToList();
    }

    private static T Decode<T>(string payload)
    {
        try
        {
            return JsonSerializer.Deserialize<T>(payload, AirtableJson.Options)
                ?? throw new AirtableException.DecodingError($"null {typeof(T).Name}");
        }
        catch (JsonException ex)
        {
            throw new AirtableException.DecodingError(ex.Message, ex);
        }
    }

    private sealed record RawEnvelope(
        string Id,
        DateTimeOffset CreatedTime,
        Dictionary<string, JsonNode?>? Fields
    );

    private sealed record RawList(List<RawEnvelope>? Records, string? Offset);
}
