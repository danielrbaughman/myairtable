using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace MyAirtable;

/// <summary>Transpiled-formula regex functions (System.Text.RegularExpressions).</summary>
public static partial class AirtableRuntime
{
    public static JsonNode? REGEX_EXTRACT(JsonNode? text, JsonNode? pattern)
    {
        var s = S(text);
        try
        {
            var m = Regex.Match(s, S(pattern));
            return JsonValue.Create(m.Success ? m.Value : "");
        }
        catch (ArgumentException)
        {
            return JsonValue.Create("");
        }
    }

    public static JsonNode? REGEX_MATCH(JsonNode? text, JsonNode? pattern)
    {
        try
        {
            return JsonValue.Create(Regex.IsMatch(S(text), S(pattern)));
        }
        catch (ArgumentException)
        {
            return JsonValue.Create(false);
        }
    }

    public static JsonNode? REGEX_REPLACE(JsonNode? text, JsonNode? pattern, JsonNode? replacement)
    {
        var s = S(text);
        try
        {
            return JsonValue.Create(Regex.Replace(s, S(pattern), S(replacement)));
        }
        catch (ArgumentException)
        {
            return JsonValue.Create(s);
        }
    }
}
