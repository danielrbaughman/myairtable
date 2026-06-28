using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json.Nodes;

namespace MyAirtable;

/// <summary>Transpiled-formula date/time functions (all UTC, via <see cref="DateTimeOffset"/>).</summary>
public static partial class AirtableRuntime
{
    private static string Iso(DateTimeOffset d) =>
        d.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture);

    private static bool IsWorkingDay(DateTimeOffset d) =>
        d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday;

    public static JsonNode? NOW() => JsonValue.Create(Iso(DateTimeOffset.UtcNow));

    public static JsonNode? TODAY()
    {
        var now = DateTimeOffset.Now;
        var startOfDay = new DateTimeOffset(now.Year, now.Month, now.Day, 0, 0, 0, now.Offset);
        return JsonValue.Create(Iso(startOfDay));
    }

    public static JsonNode? YEAR(JsonNode? value) => JsonValue.Create((long)(D(value)?.Year ?? 0));

    public static JsonNode? MONTH(JsonNode? value) =>
        JsonValue.Create((long)(D(value)?.Month ?? 0));

    public static JsonNode? DAY(JsonNode? value) => JsonValue.Create((long)(D(value)?.Day ?? 0));

    public static JsonNode? HOUR(JsonNode? value) => JsonValue.Create((long)(D(value)?.Hour ?? 0));

    public static JsonNode? MINUTE(JsonNode? value) =>
        JsonValue.Create((long)(D(value)?.Minute ?? 0));

    public static JsonNode? SECOND(JsonNode? value) =>
        JsonValue.Create((long)(D(value)?.Second ?? 0));

    /// <summary>Airtable weekday: Sunday=0 … Saturday=6 — exactly .NET's <see cref="DayOfWeek"/>.</summary>
    public static JsonNode? WEEKDAY(JsonNode? value)
    {
        var d = D(value);
        return JsonValue.Create(d is null ? 0L : (long)(int)d.Value.DayOfWeek);
    }

    public static JsonNode? DATETIME_DIFF(JsonNode? d1v, JsonNode? d2v, JsonNode? unit = null)
    {
        var d1 = D(d1v);
        var d2 = D(d2v);
        if (d1 is null || d2 is null)
            return JsonValue.Create(0L);
        var diffSecs = (d1.Value - d2.Value).TotalSeconds;
        double v;
        switch (S(unit).ToLowerInvariant())
        {
            case "milliseconds":
                v = diffSecs * 1000;
                break;
            case "seconds":
                v = diffSecs;
                break;
            case "minutes":
                v = diffSecs / 60;
                break;
            case "hours":
                v = diffSecs / 3600;
                break;
            case "weeks":
                v = diffSecs / (86400.0 * 7);
                break;
            case "months":
                return JsonValue.Create(
                    (d1.Value.Year - d2.Value.Year) * 12L + (d1.Value.Month - d2.Value.Month)
                );
            case "years":
                return JsonValue.Create((long)(d1.Value.Year - d2.Value.Year));
            default:
                v = diffSecs / 86400; // "days" and unknown units
                break;
        }
        return JsonValue.Create((long)v);
    }

    public static JsonNode? DATEADD(JsonNode? date, JsonNode? count, JsonNode? unit)
    {
        var d = D(date);
        if (d is null)
            return null;
        var n = (long)N(count);
        var z = d.Value;
        var result = S(unit).ToLowerInvariant() switch
        {
            "years" => z.AddYears((int)n),
            "months" => z.AddMonths((int)n),
            "weeks" => z.AddDays(7 * n),
            "hours" => z.AddHours(n),
            "minutes" => z.AddMinutes(n),
            "seconds" => z.AddSeconds(n),
            _ => z.AddDays(n), // "days" and unknown units
        };
        return JsonValue.Create(Iso(result));
    }

    public static JsonNode? IS_SAME(JsonNode? d1, JsonNode? d2, JsonNode? unit = null) =>
        JsonValue.Create((long)N(DATETIME_DIFF(d1, d2, unit ?? JsonValue.Create("days"))) == 0L);

    public static JsonNode? IS_BEFORE(JsonNode? d1, JsonNode? d2, JsonNode? unit = null) =>
        JsonValue.Create((long)N(DATETIME_DIFF(d1, d2, unit ?? JsonValue.Create("days"))) < 0L);

    public static JsonNode? IS_AFTER(JsonNode? d1, JsonNode? d2, JsonNode? unit = null) =>
        JsonValue.Create((long)N(DATETIME_DIFF(d1, d2, unit ?? JsonValue.Create("days"))) > 0L);

    private static string Plural(long n, string unit) => $"{n} {unit}{(n == 1L ? "" : "s")}";

    private static string HumanDuration(JsonNode? d1v, JsonNode? d2v)
    {
        var d1 = D(d1v);
        var d2 = D(d2v);
        if (d1 is null || d2 is null)
            return "";
        var diff = Math.Abs((long)((d1.Value - d2.Value).TotalSeconds));
        var minutes = diff / 60;
        var hours = minutes / 60;
        var days = hours / 24;
        var months = Math.Abs(
            (d1.Value.Year - d2.Value.Year) * 12L + (d1.Value.Month - d2.Value.Month)
        );
        var years = months / 12;
        if (years > 0)
            return Plural(years, "year");
        if (months > 0)
            return Plural(months, "month");
        if (days > 0)
            return Plural(days, "day");
        if (hours > 0)
            return Plural(hours, "hour");
        if (minutes > 0)
            return Plural(minutes, "minute");
        return Plural(diff, "second");
    }

    public static JsonNode? TONOW(JsonNode? date, JsonNode? unit = null) =>
        unit is not null
            ? DATETIME_DIFF(NOW(), date, unit)
            : JsonValue.Create(HumanDuration(date, NOW()));

    public static JsonNode? FROMNOW(JsonNode? date, JsonNode? unit = null) =>
        unit is not null
            ? DATETIME_DIFF(date, NOW(), unit)
            : JsonValue.Create(HumanDuration(date, NOW()));

    private static readonly Dictionary<string, DayOfWeek> WeeknumStartDays = new()
    {
        ["sunday"] = DayOfWeek.Sunday,
        ["monday"] = DayOfWeek.Monday,
        ["tuesday"] = DayOfWeek.Tuesday,
        ["wednesday"] = DayOfWeek.Wednesday,
        ["thursday"] = DayOfWeek.Thursday,
        ["friday"] = DayOfWeek.Friday,
        ["saturday"] = DayOfWeek.Saturday,
    };

    /// <summary>Week number of the year (week starts on the supplied day; default Sunday).</summary>
    public static JsonNode? WEEKNUM(JsonNode? date, JsonNode? startDay = null)
    {
        var d = D(date);
        if (d is null)
            return JsonValue.Create(0L);
        var first = WeeknumStartDays.GetValueOrDefault(
            S(startDay).ToLowerInvariant(),
            DayOfWeek.Sunday
        );
        var jan1 = new DateTimeOffset(d.Value.Year, 1, 1, 0, 0, 0, TimeSpan.Zero);
        // Days from the week-start to Jan 1; minimal-days-in-first-week = 1.
        var dowJan1 = ((int)jan1.DayOfWeek - (int)first + 7) % 7;
        var week = (d.Value.DayOfYear + dowJan1 - 1) / 7 + 1;
        return JsonValue.Create((long)week);
    }

    /// <summary>WORKDAY advances a date by N working days (Mon–Fri).</summary>
    public static JsonNode? WORKDAY(JsonNode? start, JsonNode? numDays)
    {
        var d = D(start);
        if (d is null)
            return null;
        var z = d.Value;
        var remaining = (int)N(numDays);
        var direction = remaining >= 0 ? 1 : -1;
        remaining = Math.Abs(remaining);
        while (remaining > 0)
        {
            z = z.AddDays(direction);
            if (IsWorkingDay(z))
                remaining -= 1;
        }
        return JsonValue.Create(Iso(z));
    }

    /// <summary>Count working days (Mon–Fri) between two dates. Signed (start later → negative).</summary>
    public static JsonNode? WORKDAY_DIFF(JsonNode? start, JsonNode? end)
    {
        var d1 = D(start);
        var d2 = D(end);
        if (d1 is null || d2 is null)
            return JsonValue.Create(0L);
        long count = 0;
        var current = d1.Value;
        var direction = d2.Value > d1.Value ? 1 : -1;
        if (IsWorkingDay(current))
            count += direction;
        while ((direction == 1 && current < d2.Value) || (direction == -1 && current > d2.Value))
        {
            current = current.AddDays(direction);
            if (IsWorkingDay(current))
                count += direction;
        }
        return JsonValue.Create(count);
    }

    /// <summary>Reinterpret a datetime in a different timezone; returns the wall-clock value as ISO.</summary>
    public static JsonNode? SET_TIMEZONE(JsonNode? date, JsonNode? tz)
    {
        var d = D(date);
        if (d is null)
            return null;
        try
        {
            var zone = TimeZoneInfo.FindSystemTimeZoneById(S(tz));
            var offset = zone.GetUtcOffset(d.Value);
            return JsonValue.Create(Iso(d.Value + offset));
        }
        catch (Exception)
        {
            return JsonValue.Create(Iso(d.Value));
        }
    }

    public static JsonNode? DATETIME_FORMAT(JsonNode? date, JsonNode? fmt = null)
    {
        var d = D(date);
        if (d is null)
            return JsonValue.Create("");
        if (fmt is null)
            return JsonValue.Create(Iso(d.Value));
        // Moment.js → .NET token mapping (the tested subset).
        var pattern = S(fmt).Replace("YYYY", "yyyy").Replace("YY", "yy").Replace("DD", "dd");
        try
        {
            return JsonValue.Create(
                d.Value.ToUniversalTime().ToString(pattern, CultureInfo.InvariantCulture)
            );
        }
        catch (FormatException)
        {
            return JsonValue.Create(Iso(d.Value));
        }
    }

    public static JsonNode? DATESTR(JsonNode? value)
    {
        var d = D(value);
        return JsonValue.Create(
            d is null
                ? ""
                : d.Value.ToUniversalTime().ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)
        );
    }

    public static JsonNode? TIMESTR(JsonNode? value)
    {
        var d = D(value);
        return JsonValue.Create(
            d is null
                ? ""
                : d.Value.ToUniversalTime().ToString("HH:mm:ss", CultureInfo.InvariantCulture)
        );
    }

    public static JsonNode? DATETIME_PARSE(JsonNode? value, JsonNode? fmt = null)
    {
        // Input-format override is ignored — D() tries ISO 8601 then a few fallbacks.
        var d = D(value);
        return d is null ? null : JsonValue.Create(Iso(d.Value));
    }
}
