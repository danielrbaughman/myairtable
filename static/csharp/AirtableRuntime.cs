using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>
/// Runtime support for transpiled Airtable formulas. This file holds the value coercions
/// (V/N/S/A/AN/AS/D/IsTruthy/IsEqual) that operate on the type-erased <see cref="JsonNode"/>; the
/// ~80 formula functions are added by F8 (partial class). JSON null is a C# <c>null</c> JsonNode
/// (no sentinel), and BLANK in every coercion.
/// </summary>
public static partial class AirtableRuntime
{
    /// <summary>
    /// Robustly read a Number-kind node as a double. Handles both JsonElement-backed nodes
    /// (from parsing) and typed <c>JsonValue&lt;long|int|decimal|double&gt;</c> (from
    /// <see cref="JsonValue.Create{T}(T, System.Text.Json.Nodes.JsonNodeOptions?)"/>), which are
    /// strict about <c>GetValue&lt;double&gt;()</c>.
    /// </summary>
    internal static double NumberOf(JsonNode node)
    {
        var v = node.AsValue();
        if (v.TryGetValue<double>(out var d))
            return d;
        if (v.TryGetValue<long>(out var l))
            return l;
        if (v.TryGetValue<decimal>(out var m))
            return (double)m;
        return double.Parse(node.ToJsonString(), CultureInfo.InvariantCulture);
    }

    /// <summary>Box any value into a <see cref="JsonNode"/> (formula literals / field refs).</summary>
    public static JsonNode? V(object? value) =>
        value switch
        {
            null => null,
            JsonNode node => node,
            DateTimeOffset dto => JsonValue.Create(
                // ISO-8601 UTC millis + 'Z' (matches AirtableDateConverter.Write); the round-trip
                // "o" format's 7-digit fractional + numeric offset is rejected by Airtable.
                dto.ToUniversalTime()
                    .ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture)
            ),
            TimeSpan ts => JsonValue.Create(ts.TotalSeconds),
            _ => JsonSerializer.SerializeToNode(value, AirtableJson.Options),
        };

    /// <summary>Coerce to a number (BLANK = 0); arrays coerce their first element.</summary>
    public static double N(JsonNode? value)
    {
        if (value is null)
            return 0.0;
        switch (value.GetValueKind())
        {
            case JsonValueKind.Number:
                return NumberOf(value);
            case JsonValueKind.String:
                return double.TryParse(
                    value.GetValue<string>().Trim(),
                    NumberStyles.Any,
                    CultureInfo.InvariantCulture,
                    out var d
                )
                    ? d
                    : 0.0;
            case JsonValueKind.True:
                return 1.0;
            case JsonValueKind.False:
                return 0.0;
            case JsonValueKind.Array:
                var arr = value.AsArray();
                return arr.Count == 0 ? 0.0 : N(arr[0]);
            default:
                return 0.0;
        }
    }

    /// <summary>Coerce to a string (BLANK = ""); whole numbers render without a decimal point.</summary>
    public static string S(JsonNode? value)
    {
        if (value is null)
            return "";
        switch (value.GetValueKind())
        {
            case JsonValueKind.String:
                return value.GetValue<string>();
            case JsonValueKind.True:
                return "1";
            case JsonValueKind.False:
                return "0";
            case JsonValueKind.Number:
                var d = NumberOf(value);
                if (double.IsFinite(d) && d == Math.Floor(d) && Math.Abs(d) < 1e15)
                    return ((long)d).ToString(CultureInfo.InvariantCulture);
                return d.ToString("R", CultureInfo.InvariantCulture);
            case JsonValueKind.Array:
                var arr = value.AsArray();
                return arr.Count == 0 ? "" : S(arr[0]);
            default:
                return "";
        }
    }

    /// <summary>Flatten args (one level): array args are spread, nulls dropped.</summary>
    public static List<JsonNode?> A(IEnumerable<JsonNode?> args)
    {
        var result = new List<JsonNode?>();
        foreach (var arg in args)
        {
            if (arg is null)
                continue;
            if (arg.GetValueKind() == JsonValueKind.Array)
            {
                foreach (var item in arg.AsArray())
                    result.Add(item);
            }
            else
            {
                result.Add(arg);
            }
        }
        return result;
    }

    public static List<double> AN(IEnumerable<JsonNode?> args) => A(args).Select(N).ToList();

    public static List<string> AS(IEnumerable<JsonNode?> args) => A(args).Select(S).ToList();

    /// <summary>Coerce to a date (BLANK = null); numbers are epoch seconds.</summary>
    public static DateTimeOffset? D(JsonNode? value)
    {
        if (value is null)
            return null;
        switch (value.GetValueKind())
        {
            case JsonValueKind.String:
                var s = value.GetValue<string>();
                return DateTimeOffset.TryParse(
                    s,
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                    out var dto
                )
                    ? dto
                    : null;
            case JsonValueKind.Number:
                return DateTimeOffset.FromUnixTimeMilliseconds((long)(NumberOf(value) * 1000));
            case JsonValueKind.Array:
                var arr = value.AsArray();
                return arr.Count == 0 ? null : D(arr[0]);
            default:
                return null;
        }
    }

    /// <summary>Airtable truthiness: BLANK/empty/0/NaN/false are falsy.</summary>
    public static bool IsTruthy(JsonNode? value)
    {
        if (value is null)
            return false;
        switch (value.GetValueKind())
        {
            case JsonValueKind.String:
                return value.GetValue<string>().Length > 0;
            case JsonValueKind.True:
                return true;
            case JsonValueKind.False:
                return false;
            case JsonValueKind.Number:
                var d = NumberOf(value);
                return d != 0.0 && !double.IsNaN(d);
            case JsonValueKind.Array:
                return value.AsArray().Count > 0;
            case JsonValueKind.Object:
                return value.AsObject().Count > 0;
            default:
                return false;
        }
    }

    /// <summary>
    /// Value equality for transpiled <c>=</c>/<c>!=</c>: numbers compared numerically, everything
    /// else by string coercion (Airtable semantics; never reference-equality on JsonNode).
    /// </summary>
    public static bool IsEqual(JsonNode? a, JsonNode? b)
    {
        if (a is null && b is null)
            return true;
        if (a is null || b is null)
            return false;
        if (a.GetValueKind() == JsonValueKind.Number && b.GetValueKind() == JsonValueKind.Number)
            return N(a) == N(b);
        return S(a) == S(b);
    }
}
