using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MyAirtable;

/// <summary>
/// Decodes Airtable date/datetime strings into <see cref="DateTimeOffset"/> (UTC). One
/// <see cref="DateTimeOffset.Parse(string, IFormatProvider, DateTimeStyles)"/> with
/// AssumeUniversal+AdjustToUniversal covers the 3 wire shapes: ISO-8601 with offset,
/// ISO-8601 without offset (assumed UTC), and date-only <c>YYYY-MM-DD</c> (→ midnight UTC).
/// Encodes as round-trip ISO-8601. Also covers <c>DateTimeOffset?</c> fields.
/// </summary>
public sealed class AirtableDateConverter : JsonConverter<DateTimeOffset>
{
    public override DateTimeOffset Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        var s = reader.GetString();
        if (string.IsNullOrEmpty(s))
            throw new AirtableException.DecodingError("empty date string");
        return DateTimeOffset.Parse(
            s,
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal
        );
    }

    public override void Write(
        Utf8JsonWriter w,
        DateTimeOffset value,
        JsonSerializerOptions options
    ) =>
        w.WriteStringValue(
            // ISO-8601 UTC with millisecond precision + 'Z' — Airtable rejects the round-trip
            // ("o") format's 7-digit fractional seconds + numeric offset on date columns. Matches
            // the wire format the other language targets emit.
            value
                .ToUniversalTime()
                .ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture)
        );
}
