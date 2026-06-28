using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>Transpiled-formula array functions.</summary>
public static partial class AirtableRuntime
{
    public static JsonNode? ARRAYJOIN(JsonNode? arr, JsonNode? separator = null)
    {
        var sep = separator is null ? ", " : S(separator);
        if (arr is null)
            return JsonValue.Create("");
        if (arr.GetValueKind() == JsonValueKind.Array)
        {
            var sb = new StringBuilder();
            var first = true;
            foreach (var v in arr.AsArray())
            {
                if (!first)
                    sb.Append(sep);
                sb.Append(S(v));
                first = false;
            }
            return JsonValue.Create(sb.ToString());
        }
        return JsonValue.Create(S(arr));
    }

    public static JsonNode? ARRAYUNIQUE(JsonNode? arr)
    {
        var @out = new JsonArray();
        if (arr is null)
            return @out;
        if (arr.GetValueKind() != JsonValueKind.Array)
        {
            @out.Add(arr.DeepClone());
            return @out;
        }
        var seen = new List<JsonNode?>();
        foreach (var v in arr.AsArray())
        {
            if (!seen.Any(x => NodeEquals(x, v)))
            {
                seen.Add(v);
                @out.Add(v?.DeepClone());
            }
        }
        return @out;
    }

    public static JsonNode? ARRAYCOMPACT(JsonNode? arr)
    {
        var @out = new JsonArray();
        if (arr is null)
            return @out;
        if (arr.GetValueKind() != JsonValueKind.Array)
        {
            @out.Add(arr.DeepClone());
            return @out;
        }
        foreach (var v in arr.AsArray())
        {
            if (v is null)
                continue;
            if (v.GetValueKind() == JsonValueKind.String && v.GetValue<string>().Length == 0)
                continue;
            @out.Add(v.DeepClone());
        }
        return @out;
    }

    public static JsonNode? ARRAYFLATTEN(JsonNode? arr)
    {
        var @out = new JsonArray();
        if (arr is null)
            return @out;
        if (arr.GetValueKind() != JsonValueKind.Array)
        {
            @out.Add(arr.DeepClone());
            return @out;
        }
        FlattenInto(arr.AsArray(), @out);
        return @out;
    }

    private static void FlattenInto(JsonArray xs, JsonArray @out)
    {
        foreach (var x in xs)
        {
            if (x is not null && x.GetValueKind() == JsonValueKind.Array)
                FlattenInto(x.AsArray(), @out);
            else
                @out.Add(x?.DeepClone());
        }
    }

    private static bool NodeEquals(JsonNode? a, JsonNode? b) =>
        (a is null && b is null) || (a is not null && b is not null && JsonNode.DeepEquals(a, b));
}
