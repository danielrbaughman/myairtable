// PHASE 0 GATE (CS1.13). Self-contained proof that the riskiest C# / System.Text.Json
// foundations of the C# target work BEFORE the real static runtime (F2) or generator (F3)
// is built. Everything here is a throwaway *prototype* under MyAirtable.Tests.Proto — it
// deliberately does NOT depend on static/csharp/, so it can never collide with the real
// types F2 introduces.
//
// Proves:
//   (a) parameterless-ctor + [JsonPropertyName]=field-ID decode, incl. computed fields via
//       [JsonInclude] + private set;
//   (b) generic JsonConverterFactory registered GLOBALLY (no field-level attributes) round-trips
//       MaybeSpecialOrError<T> / VecOrValue<T> incl. nested VecOrValue<MaybeSpecialOrError<T>>,
//       VecOrValue<DateTimeOffset> (factory -> custom date converter chain), and null-valued
//       computed decode — decode AND encode;
//   (c) TimeSpan encodes/decodes as numeric seconds, not "00:00:30";
//   (d) [JsonIgnore] snapshot + writable-only JsonObject payload builders;
//   (e) object-initializer creation for writable-only fields.

using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Xunit;

namespace MyAirtable.Tests.Proto;

// ---- Prototype sum types (records + nested sealed records -> pattern matching) ------------

public sealed record SpecialNumber(string SpecialValue);

public sealed record ErrorValue(string Error);

public abstract record MaybeSpecialOrError<T>
{
    public sealed record Value(T? Content) : MaybeSpecialOrError<T>;

    public sealed record Special(SpecialNumber Number) : MaybeSpecialOrError<T>;

    public sealed record Error(ErrorValue Err) : MaybeSpecialOrError<T>;

    /// <summary>DX accessor: the wrapped value, or default when special/error.</summary>
    public T? ValueOrDefault => this is Value v ? v.Content : default;
}

public abstract record VecOrValue<T>
{
    public sealed record Single(T? Value) : VecOrValue<T>;

    public sealed record Multiple(List<T?> Values) : VecOrValue<T>;
}

// ---- Prototype converters (generic factories, resolve nested types through options) -------

public sealed class MaybeSpecialOrErrorConverterFactory : JsonConverterFactory
{
    public override bool CanConvert(Type t) =>
        t.IsGenericType && t.GetGenericTypeDefinition() == typeof(MaybeSpecialOrError<>);

    public override JsonConverter CreateConverter(Type t, JsonSerializerOptions options)
    {
        var elem = t.GetGenericArguments()[0];
        return (JsonConverter)
            Activator.CreateInstance(typeof(MaybeSpecialOrErrorConverter<>).MakeGenericType(elem))!;
    }
}

public sealed class MaybeSpecialOrErrorConverter<T> : JsonConverter<MaybeSpecialOrError<T>>
{
    public override MaybeSpecialOrError<T> Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var el = doc.RootElement;
        if (el.ValueKind == JsonValueKind.Object)
        {
            if (el.TryGetProperty("specialValue", out var sv))
                return new MaybeSpecialOrError<T>.Special(new SpecialNumber(sv.GetString() ?? ""));
            if (el.TryGetProperty("error", out var er))
                return new MaybeSpecialOrError<T>.Error(new ErrorValue(er.GetString() ?? ""));
        }
        return new MaybeSpecialOrError<T>.Value(el.Deserialize<T>(options));
    }

    public override void Write(
        Utf8JsonWriter w,
        MaybeSpecialOrError<T> value,
        JsonSerializerOptions options
    )
    {
        switch (value)
        {
            case MaybeSpecialOrError<T>.Value v:
                JsonSerializer.Serialize(w, v.Content, options);
                break;
            case MaybeSpecialOrError<T>.Special s:
                w.WriteStartObject();
                w.WriteString("specialValue", s.Number.SpecialValue);
                w.WriteEndObject();
                break;
            case MaybeSpecialOrError<T>.Error e:
                w.WriteStartObject();
                w.WriteString("error", e.Err.Error);
                w.WriteEndObject();
                break;
        }
    }
}

public sealed class VecOrValueConverterFactory : JsonConverterFactory
{
    public override bool CanConvert(Type t) =>
        t.IsGenericType && t.GetGenericTypeDefinition() == typeof(VecOrValue<>);

    public override JsonConverter CreateConverter(Type t, JsonSerializerOptions options)
    {
        var elem = t.GetGenericArguments()[0];
        return (JsonConverter)
            Activator.CreateInstance(typeof(VecOrValueConverter<>).MakeGenericType(elem))!;
    }
}

public sealed class VecOrValueConverter<T> : JsonConverter<VecOrValue<T>>
{
    public override VecOrValue<T> Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var el = doc.RootElement;
        if (el.ValueKind == JsonValueKind.Array)
        {
            var list = new List<T?>();
            foreach (var item in el.EnumerateArray())
                list.Add(item.Deserialize<T>(options));
            return new VecOrValue<T>.Multiple(list);
        }
        return new VecOrValue<T>.Single(el.Deserialize<T>(options));
    }

    public override void Write(Utf8JsonWriter w, VecOrValue<T> value, JsonSerializerOptions options)
    {
        switch (value)
        {
            case VecOrValue<T>.Single s:
                JsonSerializer.Serialize(w, s.Value, options);
                break;
            case VecOrValue<T>.Multiple m:
                w.WriteStartArray();
                foreach (var x in m.Values)
                    JsonSerializer.Serialize(w, x, options);
                w.WriteEndArray();
                break;
        }
    }
}

/// <summary>TimeSpan &lt;-&gt; numeric seconds (Airtable duration wire format).</summary>
public sealed class AirtableDurationConverter : JsonConverter<TimeSpan>
{
    public override TimeSpan Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    ) => TimeSpan.FromSeconds(reader.GetDouble());

    public override void Write(Utf8JsonWriter w, TimeSpan value, JsonSerializerOptions options) =>
        w.WriteNumberValue(value.TotalSeconds);
}

/// <summary>Custom DateTimeOffset converter — proves the factory -> custom-converter chain
/// resolves for a value-type element inside VecOrValue&lt;DateTimeOffset&gt;.</summary>
public sealed class AirtableDateConverter : JsonConverter<DateTimeOffset>
{
    public override DateTimeOffset Read(
        ref Utf8JsonReader reader,
        Type t,
        JsonSerializerOptions options
    )
    {
        var s = reader.GetString()!;
        return DateTimeOffset.Parse(s, System.Globalization.CultureInfo.InvariantCulture);
    }

    public override void Write(
        Utf8JsonWriter w,
        DateTimeOffset value,
        JsonSerializerOptions options
    ) => w.WriteStringValue(value.ToString("o", System.Globalization.CultureInfo.InvariantCulture));
}

// ---- Prototype model (the shape the generator will emit in F4) ----------------------------

public sealed class ProtoModel
{
    [JsonPropertyName("fldText")]
    public string? Text { get; set; } // writable

    [JsonPropertyName("fldDuration")]
    public TimeSpan? Duration { get; set; } // writable

    [JsonPropertyName("fldComputed")]
    [JsonInclude]
    public MaybeSpecialOrError<double>? Computed { get; private set; } // computed: decode-only

    [JsonIgnore]
    private readonly Dictionary<string, JsonNode?> _snapshot = new();

    public ProtoModel() { } // STJ entry point + object-initializer entry

    private static readonly string[] WritableIds = { "fldText", "fldDuration" };

    public void TakeSnapshot(JsonSerializerOptions options)
    {
        _snapshot.Clear();
        foreach (var (id, val) in WritableValues(options))
            _snapshot[id] = val;
    }

    /// <summary>Writable-only create payload (computed field never included).</summary>
    public JsonObject ToCreateFields(JsonSerializerOptions options)
    {
        var obj = new JsonObject();
        foreach (var (id, val) in WritableValues(options))
            obj[id] = val;
        return obj;
    }

    /// <summary>Only writable fields whose value changed since the snapshot.</summary>
    public JsonObject DirtyFields(JsonSerializerOptions options)
    {
        var obj = new JsonObject();
        foreach (var (id, val) in WritableValues(options))
        {
            var prev = _snapshot.TryGetValue(id, out var p) ? p : null;
            if (!JsonNode.DeepEquals(prev, val))
                obj[id] = val;
        }
        return obj;
    }

    private IEnumerable<(string Id, JsonNode? Value)> WritableValues(JsonSerializerOptions options)
    {
        yield return ("fldText", Text is null ? null : JsonValue.Create(Text));
        yield return (
            "fldDuration",
            Duration is null ? null : JsonSerializer.SerializeToNode(Duration.Value, options)
        );
    }
}

// ---- The gate tests -----------------------------------------------------------------------

public class TestPocoModel
{
    private static JsonSerializerOptions Options()
    {
        var o = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        };
        // GLOBAL registration — no field-level [JsonConverter] attributes anywhere.
        o.Converters.Add(new VecOrValueConverterFactory());
        o.Converters.Add(new MaybeSpecialOrErrorConverterFactory());
        o.Converters.Add(new AirtableDurationConverter());
        o.Converters.Add(new AirtableDateConverter());
        return o;
    }

    // (a) parameterless-ctor + [JsonPropertyName] field-ID decode incl. computed private-set.
    [Fact]
    public void DecodesWritableAndComputedByFieldId()
    {
        var json = """{"fldText":"hello","fldDuration":30,"fldComputed":42.5}""";
        var m = JsonSerializer.Deserialize<ProtoModel>(json, Options())!;
        Assert.Equal("hello", m.Text);
        Assert.Equal(TimeSpan.FromSeconds(30), m.Duration);
        var v = Assert.IsType<MaybeSpecialOrError<double>.Value>(m.Computed);
        Assert.Equal(42.5, v.Content);
    }

    // (b) null-valued computed decodes to null despite WhenWritingNull on the shared options.
    [Fact]
    public void NullComputedDecodesToNull()
    {
        var m = JsonSerializer.Deserialize<ProtoModel>("""{"fldText":"x"}""", Options())!;
        Assert.Null(m.Computed);
    }

    // (b) MaybeSpecialOrError<T> Value/Special/Error round-trip for string/double/DateTimeOffset.
    [Theory]
    [InlineData("\"hi\"", typeof(MaybeSpecialOrError<string>.Value))]
    [InlineData("{\"specialValue\":\"NaN\"}", typeof(MaybeSpecialOrError<string>.Special))]
    [InlineData("{\"error\":\"#ERROR!\"}", typeof(MaybeSpecialOrError<string>.Error))]
    public void MaybeSpecialOrErrorStringRoundTrips(string json, Type expected)
    {
        var o = Options();
        var decoded = JsonSerializer.Deserialize<MaybeSpecialOrError<string>>(json, o)!;
        Assert.IsType(expected, decoded);
        var reencoded = JsonSerializer.Serialize(decoded, o);
        Assert.Equal(
            JsonNode.Parse(json)!.ToJsonString(),
            JsonNode.Parse(reencoded)!.ToJsonString()
        );
    }

    [Fact]
    public void MaybeSpecialOrErrorDoubleAndDateRoundTrip()
    {
        var o = Options();
        var d = JsonSerializer.Deserialize<MaybeSpecialOrError<double>>("3.5", o)!;
        Assert.Equal(3.5, Assert.IsType<MaybeSpecialOrError<double>.Value>(d).Content);

        var dt = JsonSerializer.Deserialize<MaybeSpecialOrError<DateTimeOffset>>(
            "\"2023-01-02T03:04:05Z\"",
            o
        )!;
        Assert.Equal(
            DateTimeOffset.Parse(
                "2023-01-02T03:04:05Z",
                System.Globalization.CultureInfo.InvariantCulture
            ),
            Assert.IsType<MaybeSpecialOrError<DateTimeOffset>.Value>(dt).Content
        );
    }

    // (b) VecOrValue<string> single + multiple, decode AND encode.
    [Fact]
    public void VecOrValueStringSingleAndMultiple()
    {
        var o = Options();
        var single = JsonSerializer.Deserialize<VecOrValue<string>>("\"a\"", o)!;
        Assert.Equal("a", Assert.IsType<VecOrValue<string>.Single>(single).Value);
        Assert.Equal("\"a\"", JsonSerializer.Serialize(single, o));

        var multi = JsonSerializer.Deserialize<VecOrValue<string>>("""["a","b"]""", o)!;
        Assert.Equal(
            new List<string?> { "a", "b" },
            Assert.IsType<VecOrValue<string>.Multiple>(multi).Values
        );
        Assert.Equal("""["a","b"]""", JsonSerializer.Serialize(multi, o));
    }

    // (b) VecOrValue<DateTimeOffset> proves the factory -> custom date converter chain.
    [Fact]
    public void VecOrValueDateUsesCustomConverter()
    {
        var o = Options();
        var v = JsonSerializer.Deserialize<VecOrValue<DateTimeOffset>>(
            """["2023-01-02T03:04:05Z"]""",
            o
        )!;
        var list = Assert.IsType<VecOrValue<DateTimeOffset>.Multiple>(v).Values;
        Assert.Single(list);
        Assert.Equal(
            DateTimeOffset.Parse(
                "2023-01-02T03:04:05Z",
                System.Globalization.CultureInfo.InvariantCulture
            ),
            list[0]
        );
    }

    // (b) nested VecOrValue<MaybeSpecialOrError<string>> decode AND encode (two-level factory chain).
    [Fact]
    public void NestedVecOrValueOfMaybeSpecialOrErrorRoundTrips()
    {
        var o = Options();
        var json = """["ok",{"error":"#ERR"},{"specialValue":"NaN"}]""";
        var v = JsonSerializer.Deserialize<VecOrValue<MaybeSpecialOrError<string>>>(json, o)!;
        var items = Assert.IsType<VecOrValue<MaybeSpecialOrError<string>>.Multiple>(v).Values;
        Assert.Equal(3, items.Count);
        Assert.IsType<MaybeSpecialOrError<string>.Value>(items[0]);
        Assert.IsType<MaybeSpecialOrError<string>.Error>(items[1]);
        Assert.IsType<MaybeSpecialOrError<string>.Special>(items[2]);
        Assert.Equal(
            JsonNode.Parse(json)!.ToJsonString(),
            JsonNode.Parse(JsonSerializer.Serialize(v, o))!.ToJsonString()
        );
    }

    // (c) TimeSpan encodes as a number of seconds, NOT "00:00:30".
    [Fact]
    public void DurationEncodesAsNumericSeconds()
    {
        var o = Options();
        var m = new ProtoModel { Duration = TimeSpan.FromSeconds(90) };
        var node = m.ToCreateFields(o);
        Assert.Equal(90.0, node["fldDuration"]!.GetValue<double>());
        Assert.DoesNotContain("00:01:30", node.ToJsonString());
    }

    // (d) snapshot + dirty + writable-only payload (computed never appears).
    [Fact]
    public void SnapshotDirtyAndCreatePayloadExcludeComputed()
    {
        var o = Options();
        var m = JsonSerializer.Deserialize<ProtoModel>("""{"fldText":"a","fldComputed":1.0}""", o)!;
        m.TakeSnapshot(o);

        // No changes -> no dirty fields.
        Assert.Empty(m.DirtyFields(o));

        m.Text = "b";
        var dirty = m.DirtyFields(o);
        Assert.True(dirty.ContainsKey("fldText"));
        Assert.False(dirty.ContainsKey("fldComputed")); // computed never in payload

        var create = m.ToCreateFields(o);
        Assert.True(create.ContainsKey("fldText"));
        Assert.False(create.ContainsKey("fldComputed"));
    }

    // (e) object-initializer creation of writable-only fields.
    [Fact]
    public void ObjectInitializerCreatesWritableFields()
    {
        var m = new ProtoModel { Text = "init", Duration = TimeSpan.FromSeconds(5) };
        Assert.Equal("init", m.Text);
        Assert.Equal(TimeSpan.FromSeconds(5), m.Duration);
        Assert.Null(m.Computed); // computed is not settable via initializer
    }
}
