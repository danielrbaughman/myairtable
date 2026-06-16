using Xunit;

namespace MyAirtable.Tests;

public class TestAirtableQueryBuild
{
    private sealed record FakeView(string Id) : IAirtableView;

    [Fact]
    public void EmptyQueryStillRequestsFieldsByFieldId()
    {
        var p = new AirtableQuery().ToParameters();
        Assert.Contains(p, kv => kv.Key == "returnFieldsByFieldId" && kv.Value == "true");
    }

    [Fact]
    public void FormulaFieldsSortMaxRecords()
    {
        var p = new AirtableQuery()
            .WithFormula("LEN({x})>0")
            .WithFields("fld1", "fld2")
            .WithSort("fld1", SortDirection.Desc)
            .WithMaxRecords(10)
            .ToParameters();

        Assert.Contains(p, kv => kv.Key == "filterByFormula" && kv.Value == "LEN({x})>0");
        Assert.Equal(2, p.Count(kv => kv.Key == "fields[]"));
        Assert.Contains(p, kv => kv.Key == "sort[0][field]" && kv.Value == "fld1");
        Assert.Contains(p, kv => kv.Key == "sort[0][direction]" && kv.Value == "desc");
        Assert.Contains(p, kv => kv.Key == "maxRecords" && kv.Value == "10");
    }

    [Fact]
    public void WithViewAcceptsIdOrTypedView()
    {
        Assert.Contains(
            new AirtableQuery().WithView("viwABC").ToParameters(),
            kv => kv.Key == "view" && kv.Value == "viwABC"
        );
        Assert.Contains(
            new AirtableQuery().WithView(new FakeView("viwXYZ")).ToParameters(),
            kv => kv.Key == "view" && kv.Value == "viwXYZ"
        );
    }

    [Fact]
    public void IsImmutable()
    {
        var q = new AirtableQuery();
        q.WithFormula("x");
        Assert.DoesNotContain(q.ToParameters(), kv => kv.Key == "filterByFormula");
    }
}
