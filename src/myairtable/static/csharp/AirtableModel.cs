using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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

    private static bool DeepEquals(JsonNode? a, JsonNode? b) =>
        (a is null && b is null) || (a is not null && b is not null && JsonNode.DeepEquals(a, b));

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
            // Structural (deep) equality — NOT AirtableRuntime.IsEqual, whose formula-style
            // coercion compares arrays by their first element only and would miss a multi-value
            // change like [a, b] -> [a].
            if (!DeepEquals(previous, value))
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
    /// Reduce attachment cells to the only shape Airtable accepts when inserting.
    /// </summary>
    /// <remarks>
    /// Airtable returns attachments carrying read-only metadata (<c>id</c>, <c>size</c>,
    /// <c>type</c>, <c>width</c>, <c>height</c>, <c>thumbnails</c>). On <b>create</b> it accepts
    /// only <c>{"url": ...}</c> (optionally with <c>"filename"</c>) — sending an <c>id</c>, alone
    /// or echoed alongside <c>url</c>, fails with <c>INVALID_ATTACHMENT_OBJECT</c>. Airtable
    /// re-ingests the file and mints a fresh attachment id, which is what makes a duplicated
    /// record's attachment independent of its source rather than an alias.
    /// <para>
    /// Create-only: on <b>update</b> an <c>id</c> is legal and means "retain this attachment".
    /// </para>
    /// <para>
    /// Cells are recognised by shape rather than by field id, so this needs no generated
    /// metadata: no other Airtable cell type is an array of objects carrying a <c>url</c>
    /// alongside an <c>att</c>-prefixed id.
    /// </para>
    /// </remarks>
    public static Dictionary<string, JsonNode?> ProjectAttachmentsForCreate(
        IReadOnlyDictionary<string, JsonNode?> fields
    )
    {
        var projectedFields = new Dictionary<string, JsonNode?>(fields.Count);
        foreach (var (key, value) in fields)
        {
            projectedFields[key] = value;
            if (value is not JsonArray items || items.Count == 0)
                continue;

            var projected = new JsonArray();
            var isAttachmentCell = true;
            foreach (var item in items)
            {
                if (
                    item is not JsonObject obj
                    || obj["url"] is not JsonNode url
                    || obj["id"] is not JsonValue idValue
                    || !idValue.TryGetValue<string>(out var id)
                    || !id.StartsWith("att", StringComparison.Ordinal)
                )
                {
                    isAttachmentCell = false;
                    break;
                }
                var entry = new JsonObject { ["url"] = url.DeepClone() };
                if (obj["filename"] is JsonNode filename)
                    entry["filename"] = filename.DeepClone();
                projected.Add(entry);
            }
            if (isAttachmentCell)
                projectedFields[key] = projected;
        }
        return projectedFields;
    }

    // ---- Copy() support -----------------------------------------------------
    //
    // The generated `public {Table}Model Copy()` is emitted INSIDE the model class (csharp.py):
    // that is the only place a computed field's `private set` is assignable, which is what lets a
    // copy carry computed values without any of them becoming publicly settable. Everything
    // table-independent lives here.
    //
    // The detach itself is structural rather than a list of un-sets: `new {Table}Model { ... }`
    // starts with a null Id (so the derived IsNew is already true), a null CreatedTime and a null
    // _snapshot, and the generated initializer names neither Id nor CreatedTime. Only
    // AttachedClient is deliberately put back, so `table.CreateAsync(record.Copy())` works without
    // the caller re-threading a client. TakeSnapshot() must never be called on a copy: a copy that
    // carried a full snapshot would diff to nothing on the next save.

    /// <summary>
    /// Reduce ONE writable attachment cell entry to the shape Airtable accepts on create —
    /// <c>{url}</c>, plus <c>{filename}</c> when the source had one.
    /// </summary>
    /// <remarks>
    /// The typed counterpart of <see cref="ProjectAttachmentsForCreate"/>, which works on an
    /// already-serialized field map. Applied at copy time because <see cref="OrmTable{T}"/>'s
    /// create path sends <see cref="ToCreateFields"/> verbatim and never projects — only
    /// <c>DuplicateAsync</c> does.
    /// </remarks>
    public static AirtableAttachment? ProjectAttachmentForCopy(AirtableAttachment? attachment) =>
        attachment is null
            ? null
            : new AirtableAttachment { Url = attachment.Url, Filename = attachment.Filename };

    /// <summary>Project every entry of a writable attachment cell (see <see cref="ProjectAttachmentForCopy"/>).</summary>
    /// <remarks>
    /// Writable cells only. A COMPUTED attachment-shaped cell — a lookup of an attachment field
    /// decodes to the identical shape — goes through <see cref="DetachForCopy{T}(VecOrValue{T}?)"/>
    /// instead and keeps its id/size/type/thumbnails: it is never written back, so stripping its
    /// metadata would lose fidelity for nothing.
    /// </remarks>
    public static List<AirtableAttachment>? ProjectAttachmentsForCopy(
        List<AirtableAttachment>? cell
    )
    {
        if (cell is null)
            return null;
        var projected = new List<AirtableAttachment>(cell.Count);
        foreach (var attachment in cell)
            projected.Add(ProjectAttachmentForCopy(attachment)!);
        return projected;
    }

    /// <summary>Deep-clone an unmodelled (<see cref="JsonNode"/>) cell so the copy can be edited in place.</summary>
    public static JsonNode? DetachForCopy(JsonNode? cell) => cell?.DeepClone();

    /// <summary>Rebuild a list cell so the copy's list is not the source's list.</summary>
    public static List<T>? DetachForCopy<T>(List<T>? cell)
    {
        if (cell is null)
            return null;
        var detached = new List<T>(cell.Count);
        foreach (var item in cell)
            // The `!` is the unconstrained-T tax: DetachLeaf is annotated
            // [NotNullIfNotNull], but flow analysis cannot see that T is not itself nullable.
            detached.Add(DetachLeaf(item)!);
        return detached;
    }

    /// <summary>
    /// Rebuild a lookup/rollup cell. <see cref="VecOrValue{T}"/> is an immutable record, but its
    /// <c>Multiple</c> case wraps a mutable <see cref="List{T}"/>.
    /// </summary>
    public static VecOrValue<T>? DetachForCopy<T>(VecOrValue<T>? cell) =>
        cell switch
        {
            null => null,
            VecOrValue<T>.Single single => new VecOrValue<T>.Single(DetachLeaf(single.Value)),
            VecOrValue<T>.Multiple multiple => new VecOrValue<T>.Multiple(
                DetachLeaves(multiple.Values)
            ),
            _ => cell,
        };

    /// <summary>
    /// Rebuild a computed lookup/rollup cell, descending through the per-entry
    /// <see cref="MaybeSpecialOrError{T}"/> wrapper.
    /// </summary>
    /// <remarks>
    /// A more specific overload than <see cref="DetachForCopy{T}(VecOrValue{T}?)"/> and chosen
    /// over it by overload resolution. It has to exist: the general one treats its elements as
    /// leaves, which would share the <see cref="JsonNode"/> inside a
    /// <c>VecOrValue&lt;MaybeSpecialOrError&lt;JsonNode&gt;&gt;</c> — the shape a computed lookup
    /// of an attachment or of an unmodelled field decodes to.
    /// </remarks>
    public static VecOrValue<MaybeSpecialOrError<T>>? DetachForCopy<T>(
        VecOrValue<MaybeSpecialOrError<T>>? cell
    ) =>
        cell switch
        {
            null => null,
            VecOrValue<MaybeSpecialOrError<T>>.Single single => new VecOrValue<
                MaybeSpecialOrError<T>
            >.Single(DetachForCopy(single.Value)),
            VecOrValue<MaybeSpecialOrError<T>>.Multiple multiple => new VecOrValue<
                MaybeSpecialOrError<T>
            >.Multiple(DetachMaybes(multiple.Values)),
            _ => cell,
        };

    /// <summary>
    /// Rebuild a computed scalar cell. The <c>Special</c>/<c>Error</c> cases carry immutable
    /// sentinels and are shared; only a <c>Value</c>'s content can be mutable.
    /// </summary>
    public static MaybeSpecialOrError<T>? DetachForCopy<T>(MaybeSpecialOrError<T>? cell) =>
        cell switch
        {
            null => null,
            MaybeSpecialOrError<T>.Value value => new MaybeSpecialOrError<T>.Value(
                DetachLeaf(value.Content)
            ),
            _ => cell,
        };

    /// <summary>
    /// Detach one leaf cell value. <see cref="JsonNode"/> is the only mutable leaf: every other
    /// type a field property can bottom out in is immutable (string, the numerics,
    /// <see cref="DateTimeOffset"/>, <see cref="TimeSpan"/>, a generated select enum, or one of
    /// the <c>init</c>-only value carriers), so it is shared. The wrappers cannot nest any deeper
    /// than this — <c>apply_csharp_computed_wrapping</c> strips a <c>List&lt;&gt;</c> before
    /// wrapping, and <c>render_type</c> never wraps an already-list type.
    /// </summary>
    [return: NotNullIfNotNull(nameof(value))]
    private static T? DetachLeaf<T>(T? value) =>
        value is JsonNode node ? (T)(object)node.DeepClone() : value;

    private static List<T?> DetachLeaves<T>(List<T?>? values)
    {
        var detached = new List<T?>(values?.Count ?? 0);
        if (values is null)
            return detached;
        foreach (var value in values)
            detached.Add(DetachLeaf(value));
        return detached;
    }

    private static List<MaybeSpecialOrError<T>?> DetachMaybes<T>(
        List<MaybeSpecialOrError<T>?>? values
    )
    {
        var detached = new List<MaybeSpecialOrError<T>?>(values?.Count ?? 0);
        if (values is null)
            return detached;
        foreach (var value in values)
            detached.Add(DetachForCopy(value));
        return detached;
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
