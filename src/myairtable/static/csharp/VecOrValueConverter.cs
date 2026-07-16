using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// Generic <see cref="JsonConverterFactory"/> for <see cref="VecOrValue{T}"/>, registered GLOBALLY
/// on the shared options. A JSON array → Multiple, anything else → Single; elements are decoded as
/// <c>T</c> through the same options, so a nested <c>VecOrValue&lt;MaybeSpecialOrError&lt;T&gt;&gt;</c>
/// resolves via the MaybeSpecialOrError factory automatically.
/// </summary>
public sealed class VecOrValueConverterFactory : JsonConverterFactory
{
    public override bool CanConvert(Type t) =>
        t.IsGenericType && t.GetGenericTypeDefinition() == typeof(VecOrValue<>);

    public override JsonConverter CreateConverter(Type t, JsonSerializerOptions options)
    {
        var elem = t.GetGenericArguments()[0];
        return (JsonConverter)
            Activator.CreateInstance(typeof(VecOrValueConverter<>).MakeGenericType(elem))!;
    }
}

public sealed class VecOrValueConverter<T> : JsonConverter<VecOrValue<T>>
{
    public override VecOrValue<T> Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var el = doc.RootElement;
        if (el.ValueKind == JsonValueKind.Array)
        {
            var list = new List<T?>();
            foreach (var item in el.EnumerateArray())
                list.Add(item.Deserialize<T>(options));
            return new VecOrValue<T>.Multiple(list);
        }
        return new VecOrValue<T>.Single(el.Deserialize<T>(options));
    }

    public override void Write(Utf8JsonWriter w, VecOrValue<T> value, JsonSerializerOptions options)
    {
        switch (value)
        {
            case VecOrValue<T>.Single s:
                JsonSerializer.Serialize(w, s.Value, options);
                break;
            case VecOrValue<T>.Multiple m:
                w.WriteStartArray();
                foreach (var x in m.Values)
                    JsonSerializer.Serialize(w, x, options);
                w.WriteEndArray();
                break;
        }
    }
}
