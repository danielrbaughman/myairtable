using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// Generic <see cref="JsonConverterFactory"/> for <see cref="MaybeSpecialOrError{T}"/>, registered
/// GLOBALLY on the shared options (no field-level attributes). Dispatches structurally:
/// <c>{"specialValue":...}</c> → Special, <c>{"error":...}</c> → Error, else the payload decoded as
/// <c>T</c> through the same options (so nested generics resolve).
/// </summary>
public sealed class MaybeSpecialOrErrorConverterFactory : JsonConverterFactory
{
    public override bool CanConvert(Type t) =>
        t.IsGenericType && t.GetGenericTypeDefinition() == typeof(MaybeSpecialOrError<>);

    public override JsonConverter CreateConverter(Type t, JsonSerializerOptions options)
    {
        var elem = t.GetGenericArguments()[0];
        return (JsonConverter)
            Activator.CreateInstance(typeof(MaybeSpecialOrErrorConverter<>).MakeGenericType(elem))!;
    }
}

public sealed class MaybeSpecialOrErrorConverter<T> : JsonConverter<MaybeSpecialOrError<T>>
{
    public override MaybeSpecialOrError<T> Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var el = doc.RootElement;
        if (el.ValueKind == JsonValueKind.Object)
        {
            if (el.TryGetProperty("specialValue", out var sv))
                return new MaybeSpecialOrError<T>.Special(new SpecialNumber(sv.GetString() ?? ""));
            if (el.TryGetProperty("error", out var er))
                return new MaybeSpecialOrError<T>.Error(new ErrorValue(er.GetString() ?? ""));
        }
        return new MaybeSpecialOrError<T>.Value(el.Deserialize<T>(options));
    }

    public override void Write(
        Utf8JsonWriter w,
        MaybeSpecialOrError<T> value,
        JsonSerializerOptions options
    )
    {
        switch (value)
        {
            case MaybeSpecialOrError<T>.Value v:
                JsonSerializer.Serialize(w, v.Content, options);
                break;
            case MaybeSpecialOrError<T>.Special s:
                w.WriteStartObject();
                w.WriteString("specialValue", s.Number.SpecialValue);
                w.WriteEndObject();
                break;
            case MaybeSpecialOrError<T>.Error e:
                w.WriteStartObject();
                w.WriteString("error", e.Err.Error);
                w.WriteEndObject();
                break;
        }
    }
}
