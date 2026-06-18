namespace MyAirtable;

/// <summary>
/// Either side of a date comparison: a literal date string or another date field. String literals
/// are accepted via dedicated overloads on <see cref="FormulaDateComparison"/> and
/// <see cref="FormulaDateField"/>.
/// </summary>
public interface IFormulaDateOperand
{
    /// <summary>The operand wrapped in <c>DATETIME_PARSE(...)</c> for comparison.</summary>
    string DatetimeParseExpr();
}

/// <summary>A literal date string operand, e.g. <c>"2025-01-15"</c>.</summary>
internal sealed class FormulaDateLiteral : IFormulaDateOperand
{
    private readonly string _value;

    public FormulaDateLiteral(string value) => _value = value;

    public string DatetimeParseExpr() =>
        "DATETIME_PARSE('" + Formulas.EscapeFormulaStringSingle(_value) + "')";
}

/// <summary>Formula builder for date fields.</summary>
public sealed class FormulaDateField : FormulaField, IFormulaDateOperand
{
    public FormulaDateField(string fieldId)
        : base(fieldId) { }

    public string DatetimeParseExpr() => "DATETIME_PARSE(" + Field() + ")";

    private FormulaDateComparison Comparison(string op) => new(FieldId, op);

    /// <summary>Date equals. Pass a date string or another date field.</summary>
    public string On(IFormulaDateOperand date) => Comparison("=").Date(date);

    public string On(string date) => On(new FormulaDateLiteral(date));

    /// <summary>Returns a <see cref="FormulaDateComparison"/> for chaining with time-ago methods.</summary>
    public FormulaDateComparison On() => Comparison("=");

    public string NotOn(IFormulaDateOperand date) => Comparison("!=").Date(date);

    public string NotOn(string date) => NotOn(new FormulaDateLiteral(date));

    public FormulaDateComparison NotOn() => Comparison("!=");

    public string OnOrAfter(IFormulaDateOperand date) => Comparison("<=").Date(date);

    public string OnOrAfter(string date) => OnOrAfter(new FormulaDateLiteral(date));

    public FormulaDateComparison OnOrAfter() => Comparison("<=");

    public string OnOrBefore(IFormulaDateOperand date) => Comparison(">=").Date(date);

    public string OnOrBefore(string date) => OnOrBefore(new FormulaDateLiteral(date));

    public FormulaDateComparison OnOrBefore() => Comparison(">=");

    public string After(IFormulaDateOperand date) => Comparison("<").Date(date);

    public string After(string date) => After(new FormulaDateLiteral(date));

    public FormulaDateComparison After() => Comparison("<");

    public string Before(IFormulaDateOperand date) => Comparison(">").Date(date);

    public string Before(string date) => Before(new FormulaDateLiteral(date));

    public FormulaDateComparison Before() => Comparison(">");

    /// <summary>Date is between start and end.</summary>
    public string Between(
        IFormulaDateOperand start,
        IFormulaDateOperand end,
        bool inclusive = true
    ) =>
        inclusive
            ? Formulas.And(OnOrAfter(start), OnOrBefore(end))
            : Formulas.And(After(start), Before(end));

    public string Between(string start, string end, bool inclusive = true) =>
        Between(new FormulaDateLiteral(start), new FormulaDateLiteral(end), inclusive);

    public string Between(string start, IFormulaDateOperand end, bool inclusive = true) =>
        Between(new FormulaDateLiteral(start), end, inclusive);

    public string Between(IFormulaDateOperand start, string end, bool inclusive = true) =>
        Between(start, new FormulaDateLiteral(end), inclusive);
}

/// <summary>Intermediate builder for date "time ago" comparisons.</summary>
public sealed class FormulaDateComparison
{
    private readonly string _fieldId;
    private readonly string _op;

    internal FormulaDateComparison(string fieldId, string op)
    {
        _fieldId = fieldId;
        _op = op;
    }

    /// <summary>Compare against another date field (or any date operand).</summary>
    public string Date(IFormulaDateOperand other) =>
        other.DatetimeParseExpr() + _op + "DATETIME_PARSE({" + _fieldId + "})";

    /// <summary>Compare against a literal date string.</summary>
    public string Date(string other) => Date(new FormulaDateLiteral(other));

    public string MillisecondsAgo(int n) => Ago(n, "milliseconds");

    public string SecondsAgo(int n) => Ago(n, "seconds");

    public string MinutesAgo(int n) => Ago(n, "minutes");

    public string HoursAgo(int n) => Ago(n, "hours");

    public string DaysAgo(int n) => Ago(n, "days");

    public string WeeksAgo(int n) => Ago(n, "weeks");

    public string MonthsAgo(int n) => Ago(n, "months");

    public string QuartersAgo(int n) => Ago(n, "quarters");

    public string YearsAgo(int n) => Ago(n, "years");

    private string Ago(int n, string unit) =>
        "DATETIME_DIFF(NOW(),{" + _fieldId + "},\"" + unit + "\")" + _op + n;
}
