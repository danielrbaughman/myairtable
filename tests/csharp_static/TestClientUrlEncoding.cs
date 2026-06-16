using Xunit;

namespace MyAirtable.Tests;

public class TestClientUrlEncoding
{
    private static readonly AirtableClient Client = new("appTEST", "keyTEST");

    [Fact]
    public void FormulaPlusEncodesAsPercent2B()
    {
        var url = Client.TableUrl(
            "tbl1",
            new[] { new KeyValuePair<string, string>("filterByFormula", "LEN({Primary Key})+1>0") }
        );
        // '+' must travel as %2B (verified live against Airtable) and spaces as %20 — never a raw '+'.
        Assert.Contains("%2B", url);
        Assert.Contains("%20", url);
        Assert.DoesNotContain("+1", url);
        Assert.DoesNotContain("Primary Key", url);
    }

    [Fact]
    public void TableIdAndBaseAreInPath()
    {
        var url = Client.TableUrl("tbl1", Array.Empty<KeyValuePair<string, string>>());
        Assert.Equal("https://api.airtable.com/v0/appTEST/tbl1", url);
    }

    [Fact]
    public void MissingCredentialsThrow()
    {
        Assert.Throws<AirtableException.MissingCredentialsError>(() => new AirtableClient("", "k"));
        Assert.Throws<AirtableException.MissingCredentialsError>(() => new AirtableClient("b", ""));
    }
}
