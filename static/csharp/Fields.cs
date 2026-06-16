using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>
/// An untyped field bag backing <c>DictTable</c>. Stores raw <see cref="JsonNode"/> values keyed by
/// field id, with dual access: <see cref="Get"/>/<see cref="Set"/> accept either a field id (tried
/// first) or a field name (resolved via the generated name→id map).
/// </summary>
public sealed class Fields
{
    private readonly Dictionary<string, JsonNode?> _storage;

    public Fields()
        : this(new Dictionary<string, JsonNode?>()) { }

    public Fields(
        Dictionary<string, JsonNode?> storage,
        IReadOnlyDictionary<string, string>? nameToId = null
    )
    {
        _storage = storage;
        NameToId = nameToId ?? new Dictionary<string, string>();
    }

    /// <summary>Field name → field id, supplied by the generated table so names resolve.</summary>
    public IReadOnlyDictionary<string, string> NameToId { get; set; }

    public int Count => _storage.Count;
    public IReadOnlyList<string> Ids => _storage.Keys.ToList();

    public IReadOnlyDictionary<string, JsonNode?> ToMap() =>
        new Dictionary<string, JsonNode?>(_storage);

    public JsonNode? Get(string key)
    {
        if (_storage.TryGetValue(key, out var direct))
            return direct;
        return NameToId.TryGetValue(key, out var id) ? _storage.GetValueOrDefault(id) : null;
    }

    public void Set(string key, JsonNode? value)
    {
        var resolved =
            _storage.ContainsKey(key) ? key
            : NameToId.TryGetValue(key, out var id) ? id
            : key;
        _storage[resolved] = value;
    }

    // ---- typed convenience accessors ----------------------------------------

    public string? GetString(string key) =>
        Get(key) is { } n && n.GetValueKind() == JsonValueKind.String ? n.GetValue<string>() : null;

    public long? GetLong(string key) =>
        Get(key) is { } n && n.GetValueKind() == JsonValueKind.Number
            ? (long)n.GetValue<double>()
            : null;

    public double? GetDouble(string key) =>
        Get(key) is { } n && n.GetValueKind() == JsonValueKind.Number ? n.GetValue<double>() : null;

    public bool? GetBoolean(string key) =>
        Get(key) is { } n && n.GetValueKind() is JsonValueKind.True or JsonValueKind.False
            ? n.GetValue<bool>()
            : null;

    public IReadOnlyList<JsonNode?>? GetArray(string key) =>
        Get(key) is { } n && n.GetValueKind() == JsonValueKind.Array ? n.AsArray().ToList() : null;

    public void SetString(string key, string? value) =>
        Set(key, value is null ? null : JsonValue.Create(value));

    public void SetLong(string key, long? value) =>
        Set(key, value is null ? null : JsonValue.Create(value.Value));

    public void SetDouble(string key, double? value) =>
        Set(key, value is null ? null : JsonValue.Create(value.Value));

    public void SetBoolean(string key, bool? value) =>
        Set(key, value is null ? null : JsonValue.Create(value.Value));

    public void SetStrings(string key, IEnumerable<string>? value) =>
        Set(
            key,
            value is null
                ? null
                : new JsonArray(value.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray())
        );

    public override bool Equals(object? obj) =>
        obj is Fields f && JsonNodeMapEquals(_storage, f._storage);

    public override int GetHashCode() => _storage.Count;

    private static bool JsonNodeMapEquals(
        Dictionary<string, JsonNode?> a,
        Dictionary<string, JsonNode?> b
    )
    {
        if (a.Count != b.Count)
            return false;
        foreach (var (k, v) in a)
        {
            if (!b.TryGetValue(k, out var other) || !JsonNode.DeepEquals(v, other))
                return false;
        }
        return true;
    }
}
