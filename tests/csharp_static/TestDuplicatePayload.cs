using System.Collections.Generic;
using System.Text.Json.Nodes;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// Airtable's create endpoint is a strict whitelist for attachments: only {url} /
/// {url, filename}. Verified against the live API — an id, alone or echoed alongside url,
/// fails with INVALID_ATTACHMENT_OBJECT.
/// </summary>
public class TestDuplicatePayload
{
    private static JsonArray ServerAttachment() =>
        new()
        {
            new JsonObject
            {
                ["id"] = "attServerSide0001",
                ["url"] = "https://example.com/a.png",
                ["filename"] = "a.png",
                ["size"] = 1234,
                ["type"] = "image/png",
                ["width"] = 10,
                ["height"] = 10,
            },
        };

    [Fact]
    public void StripsReadOnlyMetadataThatCreateRejects()
    {
        var fields = new Dictionary<string, JsonNode?> { ["fldAtt"] = ServerAttachment() };
        var projected = AirtableModel.ProjectAttachmentsForCreate(fields);

        var items = Assert.IsType<JsonArray>(projected["fldAtt"]);
        var only = Assert.IsType<JsonObject>(Assert.Single(items));
        Assert.Equal("https://example.com/a.png", only["url"]!.GetValue<string>());
        Assert.Equal("a.png", only["filename"]!.GetValue<string>());
        Assert.Null(only["id"]);
        foreach (var key in new[] { "size", "type", "width", "height" })
            Assert.Null(only[key]);
    }

    [Fact]
    public void PassesThroughCallerBuiltAttachments()
    {
        var fields = new Dictionary<string, JsonNode?>
        {
            ["fldAtt"] = new JsonArray { new JsonObject { ["url"] = "u" } },
        };
        var projected = AirtableModel.ProjectAttachmentsForCreate(fields);
        var items = Assert.IsType<JsonArray>(projected["fldAtt"]);
        Assert.Equal(
            "u",
            Assert.IsType<JsonObject>(Assert.Single(items))["url"]!.GetValue<string>()
        );
    }

    [Fact]
    public void LeavesOtherCellTypesAlone()
    {
        // Linked records, collaborators and plain arrays must not be mistaken for attachments.
        var fields = new Dictionary<string, JsonNode?>
        {
            ["fldLink"] = new JsonArray { "rec1", "rec2" },
            ["fldUser"] = new JsonObject { ["id"] = "usrX", ["email"] = "e@x.com" },
            ["fldUsers"] = new JsonArray
            {
                new JsonObject { ["id"] = "usrX", ["email"] = "e@x.com" },
            },
            ["fldEmpty"] = new JsonArray(),
            ["fldText"] = "https://example.com",
        };
        var projected = AirtableModel.ProjectAttachmentsForCreate(fields);
        foreach (var (key, value) in fields)
            Assert.Same(value, projected[key]);
    }

    [Fact]
    public void DoesNotMutateCallerFields()
    {
        var attachments = ServerAttachment();
        var fields = new Dictionary<string, JsonNode?> { ["fldAtt"] = attachments };
        AirtableModel.ProjectAttachmentsForCreate(fields);
        Assert.Equal("attServerSide0001", attachments[0]!["id"]!.GetValue<string>());
    }
}
