using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>
/// Transpiled-formula string functions. Positions/lengths count Unicode code points (the closest
/// .NET analog to the Rust/JVM targets; Swift counts grapheme clusters).
/// </summary>
public static partial class AirtableRuntime
{
    private static int CpLength(string s)
    {
        var n = 0;
        foreach (var _ in s.EnumerateRunes())
            n++;
        return n;
    }

    /// <summary>UTF-16 index after <paramref name="cpOffset"/> code points.</summary>
    private static int CpIndex(string s, int cpOffset)
    {
        var idx = 0;
        var cp = 0;
        while (cp < cpOffset && idx < s.Length)
        {
            idx +=
                char.IsHighSurrogate(s[idx])
                && idx + 1 < s.Length
                && char.IsLowSurrogate(s[idx + 1])
                    ? 2
                    : 1;
            cp++;
        }
        return idx;
    }

    public static JsonNode? LEN(JsonNode? value) => JsonValue.Create((long)CpLength(S(value)));

    public static JsonNode? LEFT(JsonNode? text, JsonNode? count)
    {
        var s = S(text);
        var n = Math.Max(0, (int)N(count));
        var end = CpIndex(s, Math.Min(n, CpLength(s)));
        return JsonValue.Create(s[..end]);
    }

    public static JsonNode? RIGHT(JsonNode? text, JsonNode? count)
    {
        var s = S(text);
        var n = Math.Max(0, (int)N(count));
        var total = CpLength(s);
        var start = CpIndex(s, total - Math.Min(n, total));
        return JsonValue.Create(s[start..]);
    }

    public static JsonNode? MID(JsonNode? text, JsonNode? start, JsonNode? count)
    {
        var s = S(text);
        var startIdx = Math.Max(0, (int)N(start) - 1);
        var len = Math.Max(0, (int)N(count));
        var total = CpLength(s);
        if (startIdx >= total)
            return JsonValue.Create("");
        var begin = CpIndex(s, startIdx);
        var end = CpIndex(s, Math.Min(startIdx + len, total));
        return JsonValue.Create(s[begin..end]);
    }

    public static JsonNode? FIND(JsonNode? needle, JsonNode? haystack, JsonNode? start = null)
    {
        var hay = S(haystack);
        var nee = S(needle);
        var offset = start is null ? 0 : Math.Max(0, (int)N(start) - 1);
        if (offset >= CpLength(hay))
            return JsonValue.Create(0L);
        var idx = hay.IndexOf(nee, CpIndex(hay, offset), StringComparison.Ordinal);
        return idx < 0 ? JsonValue.Create(0L) : JsonValue.Create((long)(CpLength(hay[..idx]) + 1));
    }

    public static JsonNode? SEARCH(JsonNode? needle, JsonNode? haystack, JsonNode? start = null)
    {
        var hay = S(haystack).ToLowerInvariant();
        var nee = S(needle).ToLowerInvariant();
        var offset = start is null ? 0 : Math.Max(0, (int)N(start) - 1);
        if (offset >= CpLength(hay))
            return JsonValue.Create(0L);
        var idx = hay.IndexOf(nee, CpIndex(hay, offset), StringComparison.Ordinal);
        return idx < 0 ? JsonValue.Create(0L) : JsonValue.Create((long)(CpLength(hay[..idx]) + 1));
    }

    public static JsonNode? SUBSTITUTE(
        JsonNode? text,
        JsonNode? oldText,
        JsonNode? newText,
        JsonNode? occurrence = null
    )
    {
        var s = S(text);
        var o = S(oldText);
        var n = S(newText);
        if (o.Length == 0)
            return JsonValue.Create(s);
        if (occurrence is null)
            return JsonValue.Create(s.Replace(o, n));
        // Replace only the Nth occurrence.
        var target = (int)N(occurrence);
        var current = 1;
        var searchFrom = 0;
        while (true)
        {
            var idx = s.IndexOf(o, searchFrom, StringComparison.Ordinal);
            if (idx < 0)
                break;
            if (current == target)
                return JsonValue.Create(s[..idx] + n + s[(idx + o.Length)..]);
            current += 1;
            searchFrom = idx + 1;
        }
        return JsonValue.Create(s);
    }

    public static JsonNode? REPLACE(
        JsonNode? text,
        JsonNode? start,
        JsonNode? count,
        JsonNode? replacement
    )
    {
        var s = S(text);
        var startIdx = Math.Max(0, (int)N(start) - 1);
        var len = Math.Max(0, (int)N(count));
        var r = S(replacement);
        var total = CpLength(s);
        if (startIdx > total)
            return JsonValue.Create(s + r);
        var begin = CpIndex(s, startIdx);
        var end = CpIndex(s, Math.Min(startIdx + len, total));
        return JsonValue.Create(s[..begin] + r + s[end..]);
    }

    public static JsonNode? LOWER(JsonNode? value) => JsonValue.Create(S(value).ToLowerInvariant());

    public static JsonNode? UPPER(JsonNode? value) => JsonValue.Create(S(value).ToUpperInvariant());

    public static JsonNode? TRIM(JsonNode? value) => JsonValue.Create(S(value).Trim());

    public static JsonNode? REPT(JsonNode? text, JsonNode? count)
    {
        var s = S(text);
        var n = Math.Max(0, (int)N(count));
        return JsonValue.Create(string.Concat(Enumerable.Repeat(s, n)));
    }

    public static JsonNode? CONCATENATE(params JsonNode?[] args)
    {
        var sb = new StringBuilder();
        foreach (var arg in args)
            sb.Append(S(arg));
        return JsonValue.Create(sb.ToString());
    }

    /// <summary>Characters NOT percent-encoded (Swift's <c>CharacterSet.urlQueryAllowed</c>).</summary>
    private const string UrlQueryAllowedExtra = "-._~!$&'()*+,;=:@/?";

    public static JsonNode? ENCODE_URL_COMPONENT(JsonNode? value)
    {
        var sb = new StringBuilder();
        foreach (var byteVal in Encoding.UTF8.GetBytes(S(value)))
        {
            var b = byteVal & 0xFF;
            var c = (char)b;
            if (b < 0x80 && (char.IsLetterOrDigit(c) || UrlQueryAllowedExtra.IndexOf(c) >= 0))
                sb.Append(c);
            else
                sb.Append('%').Append(b.ToString("X2"));
        }
        return JsonValue.Create(sb.ToString());
    }

    public static JsonNode? T(JsonNode? value) =>
        value is not null && value.GetValueKind() == JsonValueKind.String
            ? JsonValue.Create(value.GetValue<string>())
            : JsonValue.Create("");
}
