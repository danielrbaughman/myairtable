using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace MyAirtable;

/// <summary>
/// Typed record accessor for an Airtable table. Forwards all I/O to the <see cref="AirtableClient"/>;
/// decodes responses into the generated <c>{Table}Model</c> classes via STJ, attaching the client +
/// taking a snapshot on every decode so model-side <c>SaveAsync</c>/<c>DirtyFields</c> work. C#'s
/// reified generics carry the model type, so no class token is threaded (unlike the Java target).
/// </summary>
public class OrmTable<T>
    where T : AirtableModel
{
    /// <summary>Airtable's hard cap for create / update / delete batches.</summary>
    public const int BatchSize = 10;

    /// <summary>
    /// Max in-flight requests for the multi-ID <see cref="GetAsync(IReadOnlyList{string},CancellationToken)"/>
    /// fan-out. Kept just under Airtable's 5-requests-per-second limit so large ID lists don't
    /// trigger a synchronized 429 storm. Matches the Java/Kotlin targets.
    /// </summary>
    public const int MaxConcurrentGets = 4;

    private readonly string _tableId;
    private readonly AirtableClient _client;

    public OrmTable(string tableId, AirtableClient client)
    {
        _tableId = tableId;
        _client = client;
    }

    /// <summary>Result of <see cref="UpsertAsync"/>: the merged model plus whether it was inserted.</summary>
    public sealed record UpsertResult(T Model, bool WasCreated);

    // ---- decoding -----------------------------------------------------------

    /// <summary>
    /// Decode one <c>{id, createdTime, fields}</c> envelope: STJ handles <c>fields</c>; id/createdTime
    /// are copied onto the model, the client attached, and a snapshot taken.
    /// </summary>
    private T DecodeEnvelope(JsonNode? element)
    {
        try
        {
            if (element is not JsonObject obj)
                throw new AirtableException.DecodingError("expected a record object");
            var fields = obj["fields"] as JsonObject ?? new JsonObject();
            var model =
                fields.Deserialize<T>(AirtableJson.Options)
                ?? throw new AirtableException.DecodingError($"null {typeof(T).Name}");
            model.Id = obj["id"]?.GetValue<string>();
            var createdTime = obj["createdTime"];
            model.CreatedTime = createdTime is null
                ? null
                : createdTime.Deserialize<DateTimeOffset>(AirtableJson.Options);
            model.AttachedClient = _client;
            model.TakeSnapshot();
            return model;
        }
        catch (AirtableException)
        {
            throw;
        }
        catch (JsonException ex)
        {
            throw new AirtableException.DecodingError(ex.Message, ex);
        }
    }

    private static JsonNode ParseTree(string payload)
    {
        try
        {
            return JsonNode.Parse(payload)
                ?? throw new AirtableException.DecodingError("null payload");
        }
        catch (JsonException ex)
        {
            throw new AirtableException.DecodingError(ex.Message, ex);
        }
    }

    private T DecodeRecordPayload(string payload) => DecodeEnvelope(ParseTree(payload));

    /// <summary>Decode a <c>{records: [...], offset}</c> payload. Returns models + offset.</summary>
    private (List<T> Records, string? Offset) DecodeListPayload(string payload)
    {
        var obj = ParseTree(payload);
        var records = new List<T>();
        if (obj["records"] is JsonArray array)
            foreach (var record in array)
                records.Add(DecodeEnvelope(record));
        var offset = obj["offset"]?.GetValue<string>();
        return (records, string.IsNullOrEmpty(offset) ? null : offset);
    }

    // ---- get (read) ---------------------------------------------------------

    /// <summary>Fetch one record by ID.</summary>
    public async Task<T> GetAsync(string recordId, CancellationToken ct = default) =>
        DecodeRecordPayload(
            await _client.GetRecordAsync(_tableId, recordId, ct).ConfigureAwait(false)
        );

    /// <summary>
    /// Fetch many records by ID in windows of <see cref="MaxConcurrentGets"/>. Chunking bounds
    /// in-flight requests; preserves caller-supplied order.
    /// </summary>
    public async Task<List<T>> GetAsync(
        IReadOnlyList<string> recordIds,
        CancellationToken ct = default
    )
    {
        var collected = new List<T>(recordIds.Count);
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

    /// <summary>Fetch all records (default query).</summary>
    public Task<List<T>> GetAsync(CancellationToken ct = default) =>
        GetAsync(new AirtableQuery(), ct);

    /// <summary>
    /// Fetch records matching the query. Paginates internally via the <c>offset</c> continuation
    /// token; returns the merged list in page-arrival order.
    /// </summary>
    public async Task<List<T>> GetAsync(AirtableQuery query, CancellationToken ct = default)
    {
        var collected = new List<T>();
        string? offset = null;
        do
        {
            var payload = offset is null
                ? await _client.ListRecordsAsync(_tableId, query, ct).ConfigureAwait(false)
                : await FetchWithOffsetAsync(query, offset, ct).ConfigureAwait(false);
            var (records, next) = DecodeListPayload(payload);
            collected.AddRange(records);
            offset = next;
        } while (!string.IsNullOrEmpty(offset));
        return collected;
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

    // ---- create -------------------------------------------------------------

    /// <summary>
    /// Create one record. Pass a fresh model built with an object initializer (e.g.
    /// <c>new PrimaryModel { PrimaryKey = "x" }</c>); only writable fields are sent.
    /// </summary>
    public async Task<T> CreateAsync(T model, bool typecast = false, CancellationToken ct = default)
    {
        var created = await CreateBatchAsync(new[] { model.ToCreateFields() }, typecast, ct)
            .ConfigureAwait(false);
        if (created.Count == 0)
            throw new AirtableException.ApiError(
                "UNEXPECTED_RESPONSE",
                "create returned no records"
            );
        return created[0];
    }

    /// <summary>Create many records. Chunks into Airtable's batch limit (10).</summary>
    public async Task<List<T>> CreateAsync(
        IReadOnlyList<T> models,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        var payloads = models.Select(m => m.ToCreateFields()).ToList();
        var collected = new List<T>(models.Count);
        foreach (var batch in Chunk(payloads))
            collected.AddRange(await CreateBatchAsync(batch, typecast, ct).ConfigureAwait(false));
        return collected;
    }

    /// <summary>
    /// Copy a record into a brand-new record.
    /// </summary>
    /// <remarks>
    /// Every writable field is copied verbatim, including the primary field. Computed fields are
    /// omitted and recalculated by Airtable, so the copy gets its own id, autonumber and
    /// timestamps. The source model is never modified.
    /// <para>
    /// Attachments are copied by URL, so Airtable re-ingests each file and the copy owns an
    /// independent attachment rather than aliasing the source's.
    /// </para>
    /// <para>
    /// Linked records are copied as-is. Airtable link fields are many-to-many underneath, so the
    /// copy is added alongside the original on the far side of the link; the source record's own
    /// links are never modified.
    /// </para>
    /// </remarks>
    public async Task<T> DuplicateAsync(
        T model,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        var created = await CreateBatchAsync(
                new[] { AirtableModel.ProjectAttachmentsForCreate(model.ToCreateFields()) },
                typecast,
                ct
            )
            .ConfigureAwait(false);
        if (created.Count == 0)
            throw new AirtableException.ApiError(
                "UNEXPECTED_RESPONSE",
                "duplicate returned no records"
            );
        return created[0];
    }

    /// <summary>
    /// Read the record with <paramref name="recordId"/> and copy it. Costs one extra GET, and in
    /// exchange the copy reflects current server state and its attachment URLs are freshly signed
    /// (Airtable's expire after roughly two hours).
    /// </summary>
    public async Task<T> DuplicateAsync(
        string recordId,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        var source = await GetAsync(recordId, ct).ConfigureAwait(false);
        return await DuplicateAsync(source, typecast, ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Read the records with <paramref name="recordIds"/> and copy them, preserving order.
    /// </summary>
    public async Task<List<T>> DuplicateAsync(
        IReadOnlyList<string> recordIds,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        if (recordIds.Count == 0)
            return new List<T>();
        // GetAsync(IReadOnlyList<string>) already preserves caller-supplied order.
        var sources = await GetAsync(recordIds, ct).ConfigureAwait(false);
        return await DuplicateModelsAsync(sources, typecast, ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Copy several records into brand-new records. Chunks into Airtable's batch limit (10).
    /// </summary>
    /// <remarks>
    /// Named <c>DuplicateModelsAsync</c> rather than an overload of <c>DuplicateAsync</c> for the
    /// same reason <c>DeleteModelsAsync</c> exists: it would otherwise be ambiguous with the
    /// <c>IReadOnlyList&lt;string&gt;</c> id overload at the call site.
    /// </remarks>
    public async Task<List<T>> DuplicateModelsAsync(
        IReadOnlyList<T> models,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        if (models.Count == 0)
            return new List<T>();
        var payloads = models
            .Select(m => AirtableModel.ProjectAttachmentsForCreate(m.ToCreateFields()))
            .ToList();
        var collected = new List<T>(models.Count);
        foreach (var batch in Chunk(payloads))
            collected.AddRange(await CreateBatchAsync(batch, typecast, ct).ConfigureAwait(false));
        return collected;
    }

    private async Task<List<T>> CreateBatchAsync(
        IReadOnlyList<Dictionary<string, JsonNode?>> records,
        bool typecast,
        CancellationToken ct
    )
    {
        if (records.Count == 0)
            return new List<T>();
        var body = new JsonObject
        {
            ["records"] = new JsonArray(
                records
                    .Select(f => (JsonNode?)new JsonObject { ["fields"] = FieldsToJson(f) })
                    .ToArray()
            ),
            ["returnFieldsByFieldId"] = true,
        };
        // Only emit `typecast` when opted in — Airtable's server-side default is false, matching
        // the other targets.
        if (typecast)
            body["typecast"] = true;
        var payload = await _client
            .CreateRecordsAsync(_tableId, body.ToJsonString(), ct)
            .ConfigureAwait(false);
        return DecodeListPayload(payload).Records;
    }

    // ---- update -------------------------------------------------------------

    /// <summary>
    /// Update a single model. Diffs against the model's snapshot and sends only fields that changed
    /// since the last <see cref="AirtableModel.TakeSnapshot"/>.
    /// </summary>
    public async Task<T> UpdateAsync(T model, bool typecast = false, CancellationToken ct = default)
    {
        var updated = await UpdateAsync(new[] { model }, typecast, ct).ConfigureAwait(false);
        if (updated.Count == 0)
            throw new AirtableException.ApiError(
                "UNEXPECTED_RESPONSE",
                "update returned no records"
            );
        return updated[0];
    }

    /// <summary>
    /// Update many models (dirty fields only). Chunks into the batch limit. Models with no dirty
    /// fields already match server state, so they are never PATCHed — they come back unchanged, in
    /// their original positions.
    /// </summary>
    public async Task<List<T>> UpdateAsync(
        IReadOnlyList<T> models,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        if (models.Count == 0)
            return new List<T>();
        var results = new T?[models.Count];
        var dirtyIndices = new List<int>();
        var dirtyPatches = new List<(string Id, Dictionary<string, JsonNode?> Fields)>();
        for (var index = 0; index < models.Count; index++)
        {
            var model = models[index];
            if (model.IsNew)
                throw new AirtableException.ApiError(
                    "UNSAVED_MODEL",
                    "Cannot update a model without an id"
                );
            var dirty = model.DirtyFields();
            if (dirty.Count == 0)
                results[index] = model;
            else
            {
                dirtyIndices.Add(index);
                dirtyPatches.Add((model.RequireId(), dirty));
            }
        }
        var updated = new List<T>();
        foreach (var batch in Chunk(dirtyPatches))
            updated.AddRange(await UpdateBatchAsync(batch, typecast, ct).ConfigureAwait(false));
        for (var i = 0; i < dirtyIndices.Count && i < updated.Count; i++)
            results[dirtyIndices[i]] = updated[i];
        var ordered = new List<T>(results.Length);
        foreach (var result in results)
            ordered.Add(
                result
                    ?? throw new AirtableException.ApiError(
                        "UNEXPECTED_RESPONSE",
                        "update returned fewer records than requested"
                    )
            );
        return ordered;
    }

    /// <summary>Update a record's fields directly by ID (no model required).</summary>
    public async Task<T> UpdateFieldsAsync(
        string recordId,
        Dictionary<string, JsonNode?> fields,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        var updated = await UpdateBatchAsync(new[] { (recordId, fields) }, typecast, ct)
            .ConfigureAwait(false);
        if (updated.Count == 0)
            throw new AirtableException.ApiError(
                "UNEXPECTED_RESPONSE",
                "update returned no records"
            );
        return updated[0];
    }

    private async Task<List<T>> UpdateBatchAsync(
        IReadOnlyList<(string Id, Dictionary<string, JsonNode?> Fields)> patches,
        bool typecast,
        CancellationToken ct
    )
    {
        if (patches.Count == 0)
            return new List<T>();
        var body = new JsonObject
        {
            ["records"] = new JsonArray(
                patches
                    .Select(p =>
                        (JsonNode?)
                            new JsonObject { ["id"] = p.Id, ["fields"] = FieldsToJson(p.Fields) }
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
        return DecodeListPayload(payload).Records;
    }

    // ---- upsert -------------------------------------------------------------

    /// <summary>
    /// Upsert a record, matching on the supplied field IDs. Returns the merged model plus whether the
    /// record was inserted (vs updated).
    /// </summary>
    public async Task<UpsertResult> UpsertAsync(
        T model,
        IReadOnlyList<string> fieldsToMergeOn,
        bool typecast = false,
        CancellationToken ct = default
    )
    {
        var body = new JsonObject
        {
            ["records"] = new JsonArray(
                new JsonObject { ["fields"] = FieldsToJson(model.ToCreateFields()) }
            ),
            ["performUpsert"] = new JsonObject
            {
                ["fieldsToMergeOn"] = new JsonArray(
                    fieldsToMergeOn.Select(f => (JsonNode?)f).ToArray()
                ),
            },
            ["returnFieldsByFieldId"] = true,
        };
        if (typecast)
            body["typecast"] = true;
        // A merge-keyed upsert (non-empty fieldsToMergeOn) is idempotent — the key determines record
        // identity, so a retried 5xx/transport error converges. An empty merge list inserts and is
        // therefore NOT idempotent.
        var payload = await _client
            .UpdateRecordsAsync(
                _tableId,
                body.ToJsonString(),
                idempotent: fieldsToMergeOn.Count > 0,
                ct: ct
            )
            .ConfigureAwait(false);
        var obj = ParseTree(payload);
        var records = new List<T>();
        if (obj["records"] is JsonArray array)
            foreach (var record in array)
                records.Add(DecodeEnvelope(record));
        if (records.Count == 0)
            throw new AirtableException.ApiError(
                "UNEXPECTED_RESPONSE",
                "upsert returned no records"
            );
        var first = records[0];
        var wasCreated = false;
        if (obj["createdRecords"] is JsonArray created)
            foreach (var createdId in created)
                if (createdId?.GetValue<string>() == first.Id)
                    wasCreated = true;
        return new UpsertResult(first, wasCreated);
    }

    // ---- delete -------------------------------------------------------------

    /// <summary>Delete one record by ID.</summary>
    public Task DeleteAsync(string recordId, CancellationToken ct = default) =>
        _client.DeleteRecordAsync(_tableId, recordId, ct);

    /// <summary>Delete the record referenced by this model's <c>id</c>.</summary>
    public Task DeleteAsync(T model, CancellationToken ct = default)
    {
        if (model.IsNew)
            throw new AirtableException.ApiError("UNSAVED_MODEL", "Cannot delete an unsaved model");
        return DeleteAsync(model.RequireId(), ct);
    }

    /// <summary>Delete many records by ID. Chunks into Airtable's batch limit (10).</summary>
    public async Task DeleteAsync(IReadOnlyList<string> recordIds, CancellationToken ct = default)
    {
        foreach (var batch in Chunk(recordIds))
            await _client.DeleteRecordsAsync(_tableId, batch.ToList(), ct).ConfigureAwait(false);
    }

    /// <summary>Delete many records by passing their models. Chunks by ID.</summary>
    public Task DeleteModelsAsync(IReadOnlyList<T> models, CancellationToken ct = default)
    {
        var ids = new List<string>(models.Count);
        foreach (var model in models)
        {
            if (model.IsNew)
                throw new AirtableException.ApiError(
                    "UNSAVED_MODEL",
                    "Cannot delete an unsaved model"
                );
            ids.Add(model.RequireId());
        }
        return DeleteAsync(ids, ct);
    }

    // ---- helpers ------------------------------------------------------------

    private static JsonObject FieldsToJson(IReadOnlyDictionary<string, JsonNode?> fields)
    {
        var obj = new JsonObject();
        foreach (var (id, value) in fields)
            obj[id] = value?.DeepClone();
        return obj;
    }

    private static IEnumerable<IReadOnlyList<TItem>> Chunk<TItem>(IReadOnlyList<TItem> items)
    {
        for (var i = 0; i < items.Count; i += BatchSize)
            yield return items.Skip(i).Take(BatchSize).ToList();
    }
}
