namespace MyAirtable;

/// <summary>
/// An Airtable attachment. Decoded from the API; for uploads, construct with just a
/// <see cref="Url"/> (object-initializer): <c>new AirtableAttachment { Url = "https://..." }</c>.
/// </summary>
public sealed record AirtableAttachment
{
    public string? Id { get; init; }
    public string? Url { get; init; }
    public string? Filename { get; init; }
    public long? Size { get; init; }
    public string? Type { get; init; }
    public AirtableThumbnails? Thumbnails { get; init; }
}

public sealed record AirtableThumbnails(
    AirtableThumbnail? Small,
    AirtableThumbnail? Large,
    AirtableThumbnail? Full
);

public sealed record AirtableThumbnail(string? Url, long? Width, long? Height);
