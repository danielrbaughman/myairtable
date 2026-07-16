using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>Transpiled-formula logic functions (BLANK/TRUE/FALSE/IF/SWITCH/ISERROR/ERROR).</summary>
public static partial class AirtableRuntime
{
    /// <summary>The blank/empty sentinel — a C# <c>null</c> JsonNode (no NullNode in this target).</summary>
    public static JsonNode? BLANK() => null;

    public static JsonNode? TRUE() => JsonValue.Create(true);

    public static JsonNode? FALSE() => JsonValue.Create(false);

    public static JsonNode? IF(JsonNode? condition, JsonNode? ifTrue, JsonNode? ifFalse) =>
        IsTruthy(condition) ? ifTrue : ifFalse;

    /// <summary>
    /// SWITCH with the flat shape the transpiler emits: <paramref name="pairs"/> alternates
    /// (pattern, value); the default comes SECOND (so the trailing <c>params</c> can hold the
    /// pairs). Patterns match by <see cref="S(JsonNode?)"/> coercion (cross-numeric-shape parity).
    /// </summary>
    public static JsonNode? SWITCH(JsonNode? expr, JsonNode? defaultValue, params JsonNode?[] pairs)
    {
        var key = S(expr);
        for (var i = 0; i + 1 < pairs.Length; i += 2)
            if (S(pairs[i]) == key)
                return pairs[i + 1];
        return defaultValue;
    }

    /// <summary>ISERROR returns true for NaN doubles — signals a computation error.</summary>
    public static JsonNode? ISERROR(JsonNode? value)
    {
        var isNan =
            value is not null
            && value.GetValueKind() == JsonValueKind.Number
            && double.IsNaN(NumberOf(value));
        return JsonValue.Create(isNan);
    }

    /// <summary>Surface as NaN so ISERROR picks it up.</summary>
    public static JsonNode? ERROR() => JsonValue.Create(double.NaN);

    public static JsonNode? ERROR(JsonNode? message) => ERROR();
}
