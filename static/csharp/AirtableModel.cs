using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// Abstract base for every generated <c>{Table}Model</c> class. Holds the record identity
/// (<see cref="Id"/> / <see cref="CreatedTime"/>), the <see cref="AttachedClient"/> wired in by
/// the producing <see cref="OrmTable{T}"/>, and an explicit writable-field snapshot used for
/// partial-update change detection.
///
/// <para>Generated subclasses contribute their field values through the two
/// <c>Collect…</c> overrides; everything else — snapshotting, dirty diffing, payload building —
/// lives here so the generator emits no boilerplate (csharp-plan-v2 §2.3.1). STJ decodes the
/// typed auto-properties wholesale; the payload maps below are hand-rolled writable-only.</para>
/// </summary>
public abstract class AirtableModel
{
    private static readonly IReadOnlyDictionary<string, JsonNode?> EmptySnapshot =
        new Dictionary<string, JsonNode?>();

    /// <summary>Table identity. Generated models return their table's <c>TableId</c> constant.</summary>
    [JsonIgnore]
    public abstract string TableId { get; }

    /// <summary>Airtable record ID. <c>null</c> until the model has been saved; set by the table.</summary>
    [JsonIgnore]
    public string? Id { get; set; }

    /// <summary>Server-assigned creation timestamp. <c>null</c> when unsaved.</summary>
    [JsonIgnore]
    public DateTimeOffset? CreatedTime { get; set; }

    /// <summary>
    /// Client attached by the table that produced this model (after a successful decode), so the
    /// fluent <c>SaveAsync</c>/<c>FetchAsync</c>/<c>DeleteAsync</c> can call back without the caller
    /// threading a table through. Mirrors Rust's <c>ModelMeta.client</c>.
    /// </summary>
    [JsonIgnore]
    public AirtableClient? AttachedClient { get; set; }

    [JsonIgnore]
    private Dictionary<string, JsonNode?>? _snapshot;

    /// <summary><c>true</c> when the model has no server-assigned ID yet.</summary>
    [JsonIgnore]
    public bool IsNew => string.IsNullOrEmpty(Id);

    /// <summary>
    /// Current writable field values keyed by field ID. EVERY writable field appears (with a
    /// <c>null</c> value when unset) so <see cref="DirtyFields"/> can detect clears. Implemented by
    /// the generated subclass.
    /// </summary>
    protected abstract IReadOnlyDictionary<string, JsonNode?> CollectWritableFields();

    /// <summary>Current computed (read-only) field values keyed by field ID. Implemented by the generated subclass.</summary>
    protected abstract IReadOnlyDictionary<string, JsonNode?> CollectComputedFields();

    /// <summary>
    /// Capture the current writable field values so subsequent <see cref="DirtyFields"/> diffs
    /// against this point. The table snapshots on every decode, so a table-produced model starts clean.
    ///
    /// <para>Note: a save returns a FRESH, freshly-snapshotted instance; the model you called save on
    /// keeps its pre-save snapshot. Use the returned instance for further edits.</para>
    /// </summary>
    public void TakeSnapshot()
    {
        var snapshot = new Dictionary<string, JsonNode?>();
        foreach (var (id, value) in CollectWritableFields())
            snapshot[id] = value?.DeepClone();
        _snapshot = snapshot;
    }

    /// <summary>
    /// Writable fields that changed since the last <see cref="TakeSnapshot"/>, keyed by field ID.
    /// Cleared fields appear as a <c>null</c> value. Used by <see cref="OrmTable{T}"/> to PATCH only
    /// what changed.
    /// </summary>
    public Dictionary<string, JsonNode?> DirtyFields()
    {
        var snapshot = _snapshot ?? EmptySnapshot;
        var dirty = new Dictionary<string, JsonNode?>();
        foreach (var (id, value) in CollectWritableFields())
        {
            snapshot.TryGetValue(id, out var previous);
            if (!AirtableRuntime.IsEqual(previous, value))
                dirty[id] = value;
        }
        return dirty;
    }

    /// <summary>All current non-null field values (writable + computed), keyed by field ID.</summary>
    public Dictionary<string, JsonNode?> ToRecord()
    {
        var record = new Dictionary<string, JsonNode?>();
        foreach (var (id, value) in CollectWritableFields())
            if (value is not null)
                record[id] = value;
        foreach (var (id, value) in CollectComputedFields())
            if (value is not null)
                record[id] = value;
        return record;
    }

    /// <summary>
    /// Non-null <b>writable</b> field values keyed by field ID — the only path to create payloads.
    /// Computed fields never appear here.
    /// </summary>
    public Dictionary<string, JsonNode?> ToCreateFields()
    {
        var fields = new Dictionary<string, JsonNode?>();
        foreach (var (id, value) in CollectWritableFields())
            if (value is not null)
                fields[id] = value;
        return fields;
    }

    /// <summary>
    /// The server-assigned record ID, or an <see cref="AirtableException.ApiError"/> with code
    /// <c>UNSAVED_MODEL</c>. Every model returned by a table carries an ID, so prefer this over a
    /// manual null check.
    /// </summary>
    public string RequireId() =>
        IsNew
            ? throw new AirtableException.ApiError(
                "UNSAVED_MODEL",
                "Model has no server-assigned id yet"
            )
            : Id!;

    /// <summary>The attached client, or an <see cref="AirtableException.ApiError"/> with code <c>DETACHED_MODEL</c>.</summary>
    public AirtableClient RequireAttachedClient() =>
        AttachedClient
        ?? throw new AirtableException.ApiError(
            "DETACHED_MODEL",
            "Model must be obtained via a table (Get / Create / Upsert) before calling "
                + "SaveAsync / FetchAsync / DeleteAsync"
        );
}
