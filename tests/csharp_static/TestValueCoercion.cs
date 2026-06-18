using System.Text.Json.Nodes;
using Xunit;

namespace MyAirtable.Tests;

public class TestValueCoercion
{
    private static JsonNode? Parse(string json) => JsonNode.Parse(json);

    [Fact]
    public void N_CoercesAcrossKinds()
    {
        Assert.Equal(42.0, AirtableRuntime.N(Parse("42")));
        Assert.Equal(3.5, AirtableRuntime.N(Parse("3.5")));
        Assert.Equal(7.0, AirtableRuntime.N(Parse("\"7\"")));
        Assert.Equal(1.0, AirtableRuntime.N(Parse("true")));
        Assert.Equal(0.0, AirtableRuntime.N(null)); // BLANK = 0
        Assert.Equal(5.0, AirtableRuntime.N(Parse("[5,6]"))); // array → first
    }

    [Fact]
    public void S_WholeNumbersHaveNoDecimal()
    {
        Assert.Equal("42", AirtableRuntime.S(Parse("42")));
        Assert.Equal("42", AirtableRuntime.S(Parse("42.0")));
        Assert.Equal("3.5", AirtableRuntime.S(Parse("3.5")));
        Assert.Equal("hi", AirtableRuntime.S(Parse("\"hi\"")));
        Assert.Equal("", AirtableRuntime.S(null)); // BLANK = ""
    }

    [Fact]
    public void IsTruthy_MatchesAirtable()
    {
        Assert.False(AirtableRuntime.IsTruthy(null));
        Assert.False(AirtableRuntime.IsTruthy(Parse("\"\"")));
        Assert.True(AirtableRuntime.IsTruthy(Parse("\"x\"")));
        Assert.False(AirtableRuntime.IsTruthy(Parse("0")));
        Assert.True(AirtableRuntime.IsTruthy(Parse("1")));
        Assert.False(AirtableRuntime.IsTruthy(Parse("false")));
        Assert.False(AirtableRuntime.IsTruthy(Parse("[]")));
    }

    [Fact]
    public void V_BoxesValues()
    {
        Assert.Null(AirtableRuntime.V(null));
        Assert.Equal(42.0, AirtableRuntime.V(42.0)!.GetValue<double>());
        Assert.Equal("x", AirtableRuntime.V("x")!.GetValue<string>());
        var node = JsonValue.Create(5);
        Assert.Same(node, AirtableRuntime.V(node)); // JsonNode passthrough
    }

    [Fact]
    public void IsEqual_NumericVsString()
    {
        Assert.True(AirtableRuntime.IsEqual(Parse("42"), Parse("42.0")));
        Assert.True(AirtableRuntime.IsEqual(Parse("\"a\""), Parse("\"a\"")));
        Assert.False(AirtableRuntime.IsEqual(Parse("\"a\""), Parse("\"b\"")));
        Assert.True(AirtableRuntime.IsEqual(null, null));
        Assert.False(AirtableRuntime.IsEqual(null, Parse("1")));
    }

    [Fact]
    public void A_AN_AS_Flatten()
    {
        var args = new JsonNode?[] { Parse("1"), Parse("[2,3]"), null, Parse("\"4\"") };
        Assert.Equal(4, AirtableRuntime.A(args).Count);
        Assert.Equal(new List<double> { 1, 2, 3, 4 }, AirtableRuntime.AN(args));
        Assert.Equal(new List<string> { "1", "2", "3", "4" }, AirtableRuntime.AS(args));
    }

    [Fact]
    public void D_ParsesAndBlanks()
    {
        Assert.Null(AirtableRuntime.D(null));
        Assert.Equal(
            DateTimeOffset.Parse("2023-01-02T03:04:05Z"),
            AirtableRuntime.D(Parse("\"2023-01-02T03:04:05Z\""))
        );
    }
}
