using System.Text.Json;
using Xunit;

namespace MyAirtable.Tests;

public class TestDateDecoding
{
    private static DateTimeOffset Decode(string json) =>
        JsonSerializer.Deserialize<DateTimeOffset>(json, AirtableJson.Options);

    [Fact]
    public void IsoWithOffset() =>
        Assert.Equal(
            DateTimeOffset.Parse("2023-01-02T03:04:05Z").ToUniversalTime(),
            Decode("\"2023-01-02T03:04:05.000Z\"").ToUniversalTime()
        );

    [Fact]
    public void IsoAssumedUtc() =>
        Assert.Equal(
            new DateTimeOffset(2023, 1, 2, 3, 4, 5, TimeSpan.Zero),
            Decode("\"2023-01-02T03:04:05\"").ToUniversalTime()
        );

    [Fact]
    public void DateOnlyBecomesMidnightUtc() =>
        Assert.Equal(
            new DateTimeOffset(2023, 1, 2, 0, 0, 0, TimeSpan.Zero),
            Decode("\"2023-01-02\"").ToUniversalTime()
        );

    [Fact]
    public void DurationIsNumericSeconds()
    {
        var ts = JsonSerializer.Deserialize<TimeSpan>("90", AirtableJson.Options);
        Assert.Equal(TimeSpan.FromSeconds(90), ts);
        Assert.Equal(
            "90",
            JsonSerializer.Serialize(TimeSpan.FromSeconds(90), AirtableJson.Options)
        );
    }
}
