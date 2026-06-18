using System.Text.Json.Nodes;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS11.1 — DX additions: <see cref="AirtableModel.RequireId"/> / <see cref="AirtableModel.RequireAttachedClient"/>,
/// <c>MaybeSpecialOrError.ValueOrDefault</c>, <see cref="VecOrValue.CleanValues"/>, and
/// <see cref="AirtableQuery.WithView(IAirtableView)"/>. Parity with the Java/Kotlin TestDxHelpers.
///
/// <para>C# note: <c>ValueOrDefault</c> on a value-type <c>T</c> yields <c>default(T)</c> (0 for
/// double) for the Special/Error variants — so the null-unwrap parity cases use a reference
/// <c>T</c> (string), and value-variant identity is asserted instead for numeric <c>T</c>.</para>
/// </summary>
public class TestDxHelpers
{
    /// <summary>Minimal model stub — only the id/client plumbing matters here.</summary>
    private sealed class DxStubModel : AirtableModel
    {
        public override string TableId => "tblStub";

        protected override IReadOnlyDictionary<string, JsonNode?> CollectWritableFields() =>
            new Dictionary<string, JsonNode?>();

        protected override IReadOnlyDictionary<string, JsonNode?> CollectComputedFields() =>
            new Dictionary<string, JsonNode?>();
    }

    private sealed class StubView : IAirtableView
    {
        public string Id => "viwSTUB12345";
    }

    // ---- RequireId / RequireAttachedClient ----

    [Fact]
    public void RequireIdReturnsServerAssignedId()
    {
        var model = new DxStubModel { Id = "recABC123" };
        Assert.Equal("recABC123", model.RequireId());
    }

    [Fact]
    public void RequireIdThrowsUnsavedModelWhenIdIsNull()
    {
        var ex = Assert.Throws<AirtableException.ApiError>(() => new DxStubModel().RequireId());
        Assert.Equal("UNSAVED_MODEL", ex.Code);
    }

    [Fact]
    public void RequireAttachedClientThrowsDetachedWhenNull()
    {
        var ex = Assert.Throws<AirtableException.ApiError>(() =>
            new DxStubModel().RequireAttachedClient()
        );
        Assert.Equal("DETACHED_MODEL", ex.Code);
    }

    // ---- computed-field sugar ----

    [Fact]
    public void ValueOrDefaultUnwrapsValueVariant()
    {
        MaybeSpecialOrError<double> field = new MaybeSpecialOrError<double>.Value(2.5);
        Assert.Equal(2.5, field.ValueOrDefault);
    }

    [Fact]
    public void ValueOrDefaultIsNullForSpecialAndErrorVariants()
    {
        // Reference T so the non-Value default is null (mirrors the JVM boxed-null parity case).
        MaybeSpecialOrError<string> special = new MaybeSpecialOrError<string>.Special(
            new SpecialNumber("NaN")
        );
        MaybeSpecialOrError<string> error = new MaybeSpecialOrError<string>.Error(
            new ErrorValue("#ERROR!")
        );
        Assert.Null(special.ValueOrDefault);
        Assert.Null(error.ValueOrDefault);
    }

    [Fact]
    public void CleanValuesIsEmptyOnNullField()
    {
        Assert.Empty(VecOrValue.CleanValues<double>(null));
    }

    [Fact]
    public void CleanValuesUnwrapsSingleShape()
    {
        VecOrValue<MaybeSpecialOrError<double>> field = new VecOrValue<
            MaybeSpecialOrError<double>
        >.Single(new MaybeSpecialOrError<double>.Value(1.0));
        Assert.Equal(new List<double> { 1.0 }, VecOrValue.CleanValues(field));
    }

    [Fact]
    public void CleanValuesSingleSentinelCollapsesToEmpty()
    {
        VecOrValue<MaybeSpecialOrError<double>> field = new VecOrValue<
            MaybeSpecialOrError<double>
        >.Single(new MaybeSpecialOrError<double>.Error(new ErrorValue("#ERROR!")));
        Assert.Empty(VecOrValue.CleanValues(field));
    }

    [Fact]
    public void CleanValuesDropsNullsSpecialsAndErrorsFromListShape()
    {
        VecOrValue<MaybeSpecialOrError<double>> field = new VecOrValue<
            MaybeSpecialOrError<double>
        >.Multiple(
            new List<MaybeSpecialOrError<double>?>
            {
                new MaybeSpecialOrError<double>.Value(1.0),
                null,
                new MaybeSpecialOrError<double>.Special(new SpecialNumber("NaN")),
                new MaybeSpecialOrError<double>.Value(2.0),
                new MaybeSpecialOrError<double>.Error(new ErrorValue("#ERROR!")),
            }
        );
        Assert.Equal(new List<double> { 1.0, 2.0 }, VecOrValue.CleanValues(field));
    }

    [Fact]
    public void MultipleValuesIsRawAndCleanValuesIsNullSafe()
    {
        var raw = new VecOrValue<string>.Multiple(new List<string?> { "a", null, "b" });
        Assert.Equal(new List<string?> { "a", null, "b" }, raw.Values);

        VecOrValue<MaybeSpecialOrError<string>> field = new VecOrValue<
            MaybeSpecialOrError<string>
        >.Multiple(
            new List<MaybeSpecialOrError<string>?>
            {
                new MaybeSpecialOrError<string>.Value("a"),
                null,
                new MaybeSpecialOrError<string>.Value("b"),
            }
        );
        Assert.Equal(new List<string> { "a", "b" }, VecOrValue.CleanValues(field));
    }

    // ---- AirtableQuery.WithView ----

    [Fact]
    public void WithViewEncodesTheViewId()
    {
        var parameters = new AirtableQuery().WithView(new StubView()).ToParameters();
        Assert.Contains(new KeyValuePair<string, string>("view", "viwSTUB12345"), parameters);
    }

    [Fact]
    public void WithViewOverridesAnExistingView()
    {
        var query = new AirtableQuery().WithView("viwOLD").WithView(new StubView());
        Assert.Equal("viwSTUB12345", query.View);
    }
}
