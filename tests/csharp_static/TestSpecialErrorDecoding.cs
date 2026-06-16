using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

namespace MyAirtable.Tests;

public class TestSpecialErrorDecoding
{
    private static readonly JsonSerializerOptions Options = AirtableJson.Options;

    [Theory]
    [InlineData("3.5", typeof(MaybeSpecialOrError<double>.Value))]
    [InlineData("{\"specialValue\":\"NaN\"}", typeof(MaybeSpecialOrError<double>.Special))]
    [InlineData("{\"error\":\"#ERROR!\"}", typeof(MaybeSpecialOrError<double>.Error))]
    public void MaybeSpecialOrErrorDispatch(string json, Type expected)
    {
        var decoded = JsonSerializer.Deserialize<MaybeSpecialOrError<double>>(json, Options)!;
        Assert.IsType(expected, decoded);
        var reencoded = JsonSerializer.Serialize(decoded, Options);
        Assert.Equal(
            JsonNode.Parse(json)!.ToJsonString(),
            JsonNode.Parse(reencoded)!.ToJsonString()
        );
    }

    [Fact]
    public void ValueOrDefaultAccessor()
    {
        var v = JsonSerializer.Deserialize<MaybeSpecialOrError<double>>("3.5", Options)!;
        Assert.Equal(3.5, v.ValueOrDefault);
        var e = JsonSerializer.Deserialize<MaybeSpecialOrError<double>>(
            "{\"error\":\"x\"}",
            Options
        )!;
        Assert.Equal(default, e.ValueOrDefault);
    }

    [Fact]
    public void VecOrValueSingleAndMultiple()
    {
        var single = JsonSerializer.Deserialize<VecOrValue<string>>("\"a\"", Options)!;
        Assert.Equal("a", Assert.IsType<VecOrValue<string>.Single>(single).Value);
        Assert.Equal("\"a\"", JsonSerializer.Serialize(single, Options));

        var multi = JsonSerializer.Deserialize<VecOrValue<string>>("[\"a\",\"b\"]", Options)!;
        Assert.Equal(2, Assert.IsType<VecOrValue<string>.Multiple>(multi).Values.Count);
        Assert.Equal("[\"a\",\"b\"]", JsonSerializer.Serialize(multi, Options));
    }

    [Fact]
    public void NestedVecOrValueOfMaybeSpecialOrError()
    {
        var json = "[\"ok\",{\"error\":\"#E\"},{\"specialValue\":\"Infinity\"}]";
        var v = JsonSerializer.Deserialize<VecOrValue<MaybeSpecialOrError<string>>>(json, Options)!;
        var items = Assert.IsType<VecOrValue<MaybeSpecialOrError<string>>.Multiple>(v).Values;
        Assert.IsType<MaybeSpecialOrError<string>.Value>(items[0]);
        Assert.IsType<MaybeSpecialOrError<string>.Error>(items[1]);
        Assert.IsType<MaybeSpecialOrError<string>.Special>(items[2]);
        Assert.Equal(
            JsonNode.Parse(json)!.ToJsonString(),
            JsonNode.Parse(JsonSerializer.Serialize(v, Options))!.ToJsonString()
        );
    }

    [Fact]
    public void CleanValuesFlattensPresentValues()
    {
        var v = JsonSerializer.Deserialize<VecOrValue<MaybeSpecialOrError<string>>>(
            "[\"a\",{\"error\":\"x\"},\"b\"]",
            Options
        )!;
        Assert.Equal(new List<string> { "a", "b" }, VecOrValue.CleanValues(v));
        Assert.Empty(VecOrValue.CleanValues<string>(null));
    }
}
