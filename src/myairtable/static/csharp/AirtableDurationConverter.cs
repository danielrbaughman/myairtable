using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// <see cref="TimeSpan"/> ⇄ numeric seconds — Airtable's duration wire format (verified seconds,
/// not the .NET default <c>"00:00:30"</c> string). Also covers <c>TimeSpan?</c> fields.
/// </summary>
public sealed class AirtableDurationConverter : JsonConverter<TimeSpan>
{
    public override TimeSpan Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    ) => TimeSpan.FromSeconds(reader.GetDouble());

    public override void Write(Utf8JsonWriter w, TimeSpan value, JsonSerializerOptions options) =>
        w.WriteNumberValue(value.TotalSeconds);
}
