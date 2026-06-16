using Xunit;

namespace MyAirtable.Tests;

public class TestAirtableExceptionDecoding
{
    [Fact]
    public void AllSevenVariantsAreAirtableExceptions()
    {
        AirtableException[] all =
        {
            new AirtableException.HttpError(404, "missing"),
            new AirtableException.ApiError("NOT_FOUND", "no such record"),
            new AirtableException.DecodingError("bad json"),
            new AirtableException.InvalidUrlError("bad url"),
            new AirtableException.MissingCredentialsError("no key"),
            new AirtableException.NetworkError("reset"),
            new AirtableException.RateLimitedError(30),
        };
        Assert.All(all, e => Assert.IsAssignableFrom<Exception>(e));
        Assert.Equal(7, all.Length);
    }

    [Fact]
    public void HttpErrorCarriesStatusAndBody()
    {
        var e = new AirtableException.HttpError(429, "slow down");
        Assert.Equal(429, e.StatusCode);
        Assert.Equal("slow down", e.Body);
        Assert.Contains("429", e.Message);
    }

    [Fact]
    public void ApiErrorCarriesCodeAndMessage()
    {
        var e = new AirtableException.ApiError("INVALID", "nope");
        Assert.Equal("INVALID", e.Code);
        Assert.Equal("nope", e.ApiMessage);
    }

    [Fact]
    public void RateLimitedCarriesRetryAfter()
    {
        Assert.Equal(12.5, new AirtableException.RateLimitedError(12.5).RetryAfterSeconds);
        Assert.Null(new AirtableException.RateLimitedError(null).RetryAfterSeconds);
    }

    [Fact]
    public void PatternMatchesOverHierarchy()
    {
        AirtableException e = new AirtableException.HttpError(500, null);
        var label = e switch
        {
            AirtableException.HttpError h => $"http:{h.StatusCode}",
            AirtableException.RateLimitedError => "rate",
            _ => "other",
        };
        Assert.Equal("http:500", label);
    }
}
