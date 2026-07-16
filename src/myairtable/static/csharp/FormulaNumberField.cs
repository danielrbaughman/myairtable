namespace MyAirtable;

/// <summary>Formula builder for number fields.</summary>
public sealed class FormulaNumberField : FormulaField
{
    public FormulaNumberField(string fieldId)
        : base(fieldId) { }

    /// <summary>Equal to value. Named <c>Eq</c> rather than <c>Equals</c>.</summary>
    public string Eq(double value) => Field() + "=" + Formulas.Num(value);

    /// <summary>Not equal to value. Named <c>Neq</c> for symmetry with <c>Eq</c>.</summary>
    public string Neq(double value) => Field() + "!=" + Formulas.Num(value);

    /// <summary>Greater than value.</summary>
    public string GreaterThan(double value) => Field() + ">" + Formulas.Num(value);

    /// <summary>Less than value.</summary>
    public string LessThan(double value) => Field() + "<" + Formulas.Num(value);

    /// <summary>Greater than or equal to value.</summary>
    public string GreaterThanOrEquals(double value) => Field() + ">=" + Formulas.Num(value);

    /// <summary>Less than or equal to value.</summary>
    public string LessThanOrEquals(double value) => Field() + "<=" + Formulas.Num(value);

    /// <summary>Between min and max.</summary>
    public string Between(double min, double max, bool inclusive = true) =>
        inclusive
            ? Formulas.And(GreaterThanOrEquals(min), LessThanOrEquals(max))
            : Formulas.And(GreaterThan(min), LessThan(max));
}
