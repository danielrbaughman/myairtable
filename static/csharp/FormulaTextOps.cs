namespace MyAirtable;

/// <summary>Text operations shared by text, select, and lookup fields.</summary>
public abstract class FormulaTextOps : FormulaField
{
    protected FormulaTextOps(string fieldId)
        : base(fieldId) { }

    /// <summary>
    /// Field reference used in string operations (FIND/LEN with LOWER/TRIM). Lookup fields override
    /// this to wrap the reference in <c>ARRAYJOIN(field, ", ")</c> so Airtable can coerce the array
    /// to a string. Defaults to the bare <c>{field}</c> reference.
    /// </summary>
    protected virtual string StringField() => Field();

    /// <summary>
    /// Exact equality. Named <c>Eq</c> rather than <c>Equals</c> because <c>Equals(value)</c> would
    /// overload <see cref="object.Equals(object)"/> and silently resolve to the wrong method.
    /// </summary>
    public string Eq(string value, bool caseSensitive = true, bool trim = false) =>
        Formulas.WrapField(Field(), caseSensitive, trim)
        + "="
        + Formulas.WrapValueStr(value, caseSensitive, trim);

    /// <summary>Equals any of the given values.</summary>
    public string EqualsAny(
        IEnumerable<string> values,
        bool caseSensitive = true,
        bool trim = false
    ) => Formulas.Or(values.Select(v => Eq(v, caseSensitive, trim)));

    /// <summary>Not equal. Named <c>Neq</c> for symmetry with <c>Eq</c>.</summary>
    public string Neq(string value, bool caseSensitive = true, bool trim = false) =>
        Formulas.WrapField(Field(), caseSensitive, trim)
        + "!="
        + Formulas.WrapValueStr(value, caseSensitive, trim);

    /// <summary>Contains substring.</summary>
    public string Contains(string value, bool caseSensitive = true, bool trim = false) =>
        "FIND("
        + Formulas.WrapValueStr(value, caseSensitive, trim)
        + ","
        + Formulas.WrapField(StringField(), caseSensitive, trim)
        + ")>0";

    /// <summary>Contains any of the given values.</summary>
    public string ContainsAny(
        IEnumerable<string> values,
        bool caseSensitive = true,
        bool trim = false
    ) => Formulas.Or(values.Select(v => Contains(v, caseSensitive, trim)));

    /// <summary>Contains all of the given values.</summary>
    public string ContainsAll(
        IEnumerable<string> values,
        bool caseSensitive = true,
        bool trim = false
    ) => Formulas.And(values.Select(v => Contains(v, caseSensitive, trim)));

    /// <summary>Does not contain substring.</summary>
    public string NotContains(string value, bool caseSensitive = true, bool trim = false) =>
        Formulas.Not(Contains(value, caseSensitive, trim));

    /// <summary>Starts with the given value.</summary>
    public string StartsWith(string value, bool caseSensitive = true, bool trim = false) =>
        "FIND("
        + Formulas.WrapValueStr(value, caseSensitive, trim)
        + ","
        + Formulas.WrapField(StringField(), caseSensitive, trim)
        + ")=1";

    /// <summary>Does not start with the given value.</summary>
    public string NotStartsWith(string value, bool caseSensitive = true, bool trim = false) =>
        "FIND("
        + Formulas.WrapValueStr(value, caseSensitive, trim)
        + ","
        + Formulas.WrapField(StringField(), caseSensitive, trim)
        + ")!=1";

    /// <summary>Ends with the given value.</summary>
    public string EndsWith(string value, bool caseSensitive = true, bool trim = false)
    {
        var f = Formulas.WrapField(StringField(), caseSensitive, trim);
        var v = Formulas.WrapValueStr(value, caseSensitive, trim);
        return "FIND(" + v + "," + f + ")=LEN(" + f + ")-LEN(" + v + ")+1";
    }

    /// <summary>Does not end with the given value.</summary>
    public string NotEndsWith(string value, bool caseSensitive = true, bool trim = false)
    {
        var f = Formulas.WrapField(StringField(), caseSensitive, trim);
        var v = Formulas.WrapValueStr(value, caseSensitive, trim);
        return "FIND(" + v + "," + f + ")!=LEN(" + f + ")-LEN(" + v + ")+1";
    }

    /// <summary>Phone number equality (strips spaces, dashes, parens, plus, dots).</summary>
    public string PhoneEquals(string value)
    {
        var normalized = new string(value.Where(c => " -().+".IndexOf(c) < 0).ToArray());
        var stripped =
            "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE("
            + Field()
            + ",\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")";
        return stripped + "=\"" + Formulas.EscapeFormulaString(normalized) + "\"";
    }

    /// <summary>Regex match.</summary>
    public string RegexMatch(string pattern) =>
        // Escape for the formula-string context only; regex escapes like \d become \\d in the
        // formula source, which Airtable's parser unescapes before handing the pattern to the engine.
        "REGEX_MATCH(" + Field() + ",\"" + Formulas.EscapeFormulaString(pattern) + "\")";
}
