using System.Text.Json;
using System.Text.Json.Nodes;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS5.1/5.2/5.4 — value-carrier (de)serialization. The carriers carry no [JsonPropertyName],
/// so the global camelCase naming policy maps them to Airtable's wire shape (url, profilePicUrl,
/// …). Critical for writes: a URL-based attachment create sends <c>{"url": ...}</c> and a
/// collaborator write sends <c>{"id": ...}</c>.
/// </summary>
public class TestValueCarriers
{
    private static string Encode<T>(T value) =>
        JsonSerializer.Serialize(value, AirtableJson.Options);

    private static T Decode<T>(string json) =>
        JsonSerializer.Deserialize<T>(json, AirtableJson.Options)!;

    // ---- attachments (CS5.1) ----

    [Fact]
    public void AttachmentUrlOnlyEncodesToCamelCaseUrlOnly()
    {
        var node = JsonNode.Parse(
            Encode(new AirtableAttachment { Url = "https://example.com/a.png" })
        )!;
        Assert.Equal("https://example.com/a.png", node["url"]!.GetValue<string>());
        // null fields omitted (WhenWritingNull) — a clean URL-based upload payload.
        Assert.Null(node["id"]);
        Assert.Null(node["filename"]);
    }

    [Fact]
    public void AttachmentDecodesFullWireShapeIncludingThumbnails()
    {
        var model = Decode<AirtableAttachment>(
            """
            {
              "id": "att123",
              "url": "https://example.com/a.png",
              "filename": "a.png",
              "size": 2048,
              "type": "image/png",
              "thumbnails": { "small": { "url": "https://example.com/s.png", "width": 36, "height": 36 } }
            }
            """
        );
        Assert.Equal("att123", model.Id);
        Assert.Equal("a.png", model.Filename);
        Assert.Equal(2048, model.Size);
        Assert.Equal("image/png", model.Type);
        Assert.Equal("https://example.com/s.png", model.Thumbnails!.Small!.Url);
        Assert.Equal(36, model.Thumbnails.Small.Width);
    }

    // ---- collaborators (CS5.2) ----

    [Fact]
    public void CollaboratorIdOnlyEncodesToCamelCaseIdOnly()
    {
        var node = JsonNode.Parse(Encode(new AirtableCollaborator { Id = "usr123" }))!;
        Assert.Equal("usr123", node["id"]!.GetValue<string>());
        Assert.Null(node["email"]);
        Assert.Null(node["name"]);
    }

    [Fact]
    public void CollaboratorDecodesProfilePicUrlFromCamelCase()
    {
        var model = Decode<AirtableCollaborator>(
            """
            { "id": "usr1", "email": "a@b.c", "name": "Ada", "profilePicUrl": "https://example.com/p.png" }
            """
        );
        Assert.Equal("usr1", model.Id);
        Assert.Equal("a@b.c", model.Email);
        Assert.Equal("Ada", model.Name);
        Assert.Equal("https://example.com/p.png", model.ProfilePicUrl);
    }

    // ---- buttons (CS5.4) ----

    [Fact]
    public void ButtonDecodesLabelAndUrl()
    {
        var model = Decode<AirtableButton>("""{ "label": "Open", "url": "https://example.com" }""");
        Assert.Equal("Open", model.Label);
        Assert.Equal("https://example.com", model.Url);
    }
}
