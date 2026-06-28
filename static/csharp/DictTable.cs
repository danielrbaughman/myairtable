using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace MyAirtable;

/// <summary>
/// Untyped table facade: raw CRUD over <see cref="Fields"/> bags. Pairs with the generated
/// <c>OrmTable&lt;T&gt;</c> (F4) over the same <see cref="AirtableClient"/>. Mutating writes are
/// chunked into batches of <see cref="BatchSize"/> (the Airtable limit).
/// </summary>
public sealed class DictTable
{
    public const int BatchSize = 10;

    /// <summary>
    /// Max in-flight requests for the multi-ID <see cref="GetAsync(IReadOnlyList{string},CancellationToken)"/>
    /// fan-out. Kept just under Airtable's 5-requests-per-second limit so large ID lists don't
    /// trigger a synchronized 429 storm. Matches <see cref="OrmTable{T}.MaxConcurrentGets"/> and the
    /// Java/Kotlin targets.
    /// </summary>
    public const int MaxConcurrentGets = 4;

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

    /// <summary>
    /// Fetch many records by id in windows of <see cref="MaxConcurrentGets"/>. Chunking bounds
    /// in-flight requests so a large id list can't trigger a 429 storm; preserves caller order.
    /// </summary>
    public async Task<List<Record>> GetAsync(
        IReadOnlyList<string> recordIds,
        CancellationToken ct = default
    )
    {
        var collected = new List<Record>(recordIds.Count);
        for (var start = 0; start < recordIds.Count; start += MaxConcurrentGets)
        {
            var window = recordIds
                .Skip(start)
                .Take(MaxConcurrentGets)
                .Select(id => GetAsync(id, ct))
                .ToList();
            collected.AddRange(await Task.WhenAll(window).ConfigureAwait(false));
        }
        return collected;
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
        return _client.SendAsync(
            HttpMethod.Get,
            _client.TableUrl(_tableId, pars),
            null,
            idempotent: true,
            ct
        );
    }

    // ---- creates ------------------------------------------------------------

    public async Task<Record> CreateAsync(
        Fields fields,
        bool typecast = false,
        CancellationToken ct = default
    ) => (await CreateAsync(new[] { fields }, typecast, ct).ConfigureAwait(false))[0];

    public async Task<List<Record>> CreateAsync(
        IReadOnlyList<Fields> fields,
        bool typecast = false,
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
            if (typecast)
                body["typecast"] = true;
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
        bool typecast = false,
        CancellationToken ct = default
    ) =>
        (
            await UpdateAsync(new[] { new Update(recordId, fields) }, typecast, ct)
                .ConfigureAwait(false)
        )[0];

    public async Task<List<Record>> UpdateAsync(
        IReadOnlyList<Update> updates,
        bool typecast = false,
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
            if (typecast)
                body["typecast"] = true;
            var payload = await _client
                .UpdateRecordsAsync(_tableId, body.ToJsonString(), ct: ct)
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
