using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>Transpiled-formula math functions.</summary>
public static partial class AirtableRuntime
{
    /// <summary>Round half away from zero (Swift's <c>Double.rounded()</c>).</summary>
    private static double RoundHalfAwayFromZero(double d) =>
        d >= 0 ? Math.Floor(d + 0.5) : Math.Ceiling(d - 0.5);

    /// <summary>Whole-number results emit as integral (long) nodes, mirroring the other targets.</summary>
    private static JsonNode NumValue(double d) =>
        double.IsFinite(d) && d == Math.Floor(d) && Math.Abs(d) < 1e15
            ? JsonValue.Create((long)d)
            : JsonValue.Create(d);

    public static JsonNode? SUM(params JsonNode?[] args)
    {
        var total = 0.0;
        foreach (var n in AN(args))
            total += n;
        return NumValue(total);
    }

    public static JsonNode? AVERAGE(params JsonNode?[] args)
    {
        var nums = AN(args);
        if (nums.Count == 0)
            return JsonValue.Create(double.NaN);
        return NumValue(nums.Sum() / nums.Count);
    }

    public static JsonNode? MIN(params JsonNode?[] args)
    {
        var nums = AN(args);
        return nums.Count == 0 ? JsonValue.Create(double.NaN) : NumValue(nums.Min());
    }

    public static JsonNode? MAX(params JsonNode?[] args)
    {
        var nums = AN(args);
        return nums.Count == 0 ? JsonValue.Create(double.NaN) : NumValue(nums.Max());
    }

    public static JsonNode? COUNT(params JsonNode?[] args)
    {
        long c = 0;
        foreach (var v in A(args))
            if (v is not null && v.GetValueKind() == JsonValueKind.Number)
                c += 1;
        return JsonValue.Create(c);
    }

    public static JsonNode? COUNTA(params JsonNode?[] args)
    {
        long c = 0;
        foreach (var v in A(args))
        {
            if (v is null)
                continue;
            if (v.GetValueKind() == JsonValueKind.String && v.GetValue<string>().Length == 0)
                continue;
            c += 1;
        }
        return JsonValue.Create(c);
    }

    public static JsonNode? ROUND(JsonNode? value, JsonNode? precision = null)
    {
        var factor = Math.Pow(10.0, (int)N(precision));
        return NumValue(RoundHalfAwayFromZero(N(value) * factor) / factor);
    }

    public static JsonNode? ROUNDUP(JsonNode? value, JsonNode? precision = null)
    {
        var n = N(value);
        var factor = Math.Pow(10.0, (int)N(precision));
        return NumValue(
            n >= 0 ? Math.Ceiling(n * factor) / factor : Math.Floor(n * factor) / factor
        );
    }

    public static JsonNode? ROUNDDOWN(JsonNode? value, JsonNode? precision = null)
    {
        var n = N(value);
        var factor = Math.Pow(10.0, (int)N(precision));
        return NumValue(
            n >= 0 ? Math.Floor(n * factor) / factor : Math.Ceiling(n * factor) / factor
        );
    }

    public static JsonNode? CEILING(JsonNode? value, JsonNode? significance = null)
    {
        var s = significance is null ? 1.0 : N(significance);
        var sig = s == 0.0 ? 1.0 : s;
        return NumValue(Math.Ceiling(N(value) / sig) * sig);
    }

    public static JsonNode? FLOOR(JsonNode? value, JsonNode? significance = null)
    {
        var s = significance is null ? 1.0 : N(significance);
        var sig = s == 0.0 ? 1.0 : s;
        return NumValue(Math.Floor(N(value) / sig) * sig);
    }

    public static JsonNode? LOG(JsonNode? value, JsonNode? @base = null)
    {
        var n = N(value);
        return @base is not null
            ? NumValue(Math.Log(n) / Math.Log(N(@base)))
            : NumValue(Math.Log10(n));
    }

    public static JsonNode? EVEN(JsonNode? value)
    {
        var n = N(value);
        var c = Math.Ceiling(Math.Abs(n));
        var r = c % 2.0 == 0.0 ? c : c + 1;
        if (n < 0)
            r = -r;
        return JsonValue.Create((long)r);
    }

    public static JsonNode? ODD(JsonNode? value)
    {
        var n = N(value);
        var c = Math.Ceiling(Math.Abs(n));
        var r = c % 2.0 == 1.0 ? c : c + 1;
        if (n < 0)
            r = -r;
        return JsonValue.Create((long)r);
    }

    public static JsonNode? VALUE(JsonNode? value)
    {
        if (value is null)
            return JsonValue.Create(0L);
        var s = S(value);
        if (s.Contains('.'))
        {
            if (double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var d))
                return JsonValue.Create(d);
        }
        else if (long.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var l))
        {
            return JsonValue.Create(l);
        }
        return JsonValue.Create(double.NaN);
    }

    public static JsonNode? POWER(JsonNode? @base, JsonNode? exp) =>
        NumValue(Math.Pow(N(@base), N(exp)));

    public static JsonNode? MOD(JsonNode? value, JsonNode? divisor)
    {
        var d = N(divisor);
        return d == 0.0 ? JsonValue.Create(double.NaN) : NumValue(N(value) % d);
    }

    public static JsonNode? ABS(JsonNode? value) => NumValue(Math.Abs(N(value)));

    public static JsonNode? EXP(JsonNode? value)
    {
        var n = N(value);
        // .NET Math.Exp(1.0), like the JVM, is one ULP above Math.E; V8 (and therefore Airtable)
        // returns the correctly-rounded E. Pin the integer-1 case so local eval matches the API.
        return NumValue(n == 1.0 ? Math.E : Math.Exp(n));
    }

    public static JsonNode? SQRT(JsonNode? value) => NumValue(Math.Sqrt(N(value)));

    public static JsonNode? INT(JsonNode? value) => JsonValue.Create((long)Math.Floor(N(value)));
}
