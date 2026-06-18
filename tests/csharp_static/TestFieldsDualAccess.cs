using System.Text.Json.Nodes;
using Xunit;

namespace MyAirtable.Tests;

public class TestFieldsDualAccess
{
    private static Fields Make() =>
        new(
            new Dictionary<string, JsonNode?> { ["fld001"] = JsonValue.Create("hello") },
            new Dictionary<string, string> { ["Name"] = "fld001" }
        );

    [Fact]
    public void GetByIdAndByName()
    {
        var f = Make();
        Assert.Equal("hello", f.Get("fld001")!.GetValue<string>());
        Assert.Equal("hello", f.Get("Name")!.GetValue<string>()); // name → id fallback
        Assert.Null(f.Get("Unknown"));
    }

    [Fact]
    public void SetByNameResolvesToId()
    {
        var f = Make();
        f.SetString("Name", "world");
        Assert.Equal("world", f.GetString("fld001"));
        Assert.Single(f.Ids);
        Assert.Equal("fld001", f.Ids[0]);
    }

    [Fact]
    public void SetByUnknownKeyKeepsKey()
    {
        var f = new Fields();
        f.SetLong("fld999", 42);
        Assert.Equal(42, f.GetLong("fld999"));
    }

    [Fact]
    public void TypedAccessors()
    {
        var f = new Fields();
        f.SetDouble("a", 3.5);
        f.SetBoolean("b", true);
        f.SetStrings("c", new[] { "x", "y" });
        Assert.Equal(3.5, f.GetDouble("a"));
        Assert.True(f.GetBoolean("b"));
        Assert.Equal(2, f.GetArray("c")!.Count);
        Assert.Null(f.GetString("missing"));
    }
}
