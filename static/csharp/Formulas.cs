using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace MyAirtable;

/// <summary>Top-level formula combinators matching Airtable's logical functions.</summary>
public static class Formulas
{
    /// <summary>Combine formulas with AND logic. Empty strings are filtered out.</summary>
    public static string And(params string[] args) => And((IEnumerable<string>)args);

    public static string And(IEnumerable<string> args) => Combine("AND", args);

    /// <summary>Combine formulas with OR logic. Empty strings are filtered out.</summary>
    public static string Or(params string[] args) => Or((IEnumerable<string>)args);

    public static string Or(IEnumerable<string> args) => Combine("OR", args);

    /// <summary>Exclusive OR. Empty strings are filtered out.</summary>
    public static string Xor(params string[] args) => Xor((IEnumerable<string>)args);

    public static string Xor(IEnumerable<string> args) => Combine("XOR", args);

    /// <summary>Negate a formula.</summary>
    public static string Not(string formula) => "NOT(" + formula + ")";

    private static string Combine(string fn, IEnumerable<string> args)
    {
        var filtered = args.Where(a => !string.IsNullOrEmpty(a)).ToList();
        return filtered.Count switch
        {
            0 => "",
            1 => filtered[0],
            _ => $"{fn}({string.Join(",", filtered)})",
        };
    }

    // ---- shared escaping / wrapping helpers (internal) ----

    /// <summary>
    /// Escape a value for an Airtable double-quoted formula string. Backslashes are escaped FIRST,
    /// then quotes — otherwise a trailing <c>\</c> leaves the closing quote live and the remainder
    /// of the value executes as formula code.
    /// </summary>
    internal static string EscapeFormulaString(string value) =>
        value.Replace("\\", "\\\\").Replace("\"", "\\\"");

    /// <summary>Escape a value for an Airtable single-quoted formula string.</summary>
    internal static string EscapeFormulaStringSingle(string value) =>
        value.Replace("\\", "\\\\").Replace("'", "\\'");

    /// <summary>Format a number for a formula (invariant culture — no locale separators).</summary>
    internal static string Num(double value) => value.ToString(CultureInfo.InvariantCulture);

    internal static string WrapField(string field, bool caseSensitive, bool trim)
    {
        var v = field;
        if (trim)
            v = "TRIM(" + v + ")";
        if (!caseSensitive)
            v = "LOWER(" + v + ")";
        return v;
    }

    internal static string WrapValueStr(string value, bool caseSensitive, bool trim)
    {
        var v = "\"" + EscapeFormulaString(value) + "\"";
        if (trim)
            v = "TRIM(" + v + ")";
        if (!caseSensitive)
            v = "LOWER(" + v + ")";
        return v;
    }
}
