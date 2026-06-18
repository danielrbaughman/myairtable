namespace MyAirtable;

/// <summary>Formula builder for checkbox/boolean fields.</summary>
public sealed class FormulaBooleanField : FormulaField
{
    public FormulaBooleanField(string fieldId)
        : base(fieldId) { }

    /// <summary>Equal to boolean value. Named <c>Eq</c> rather than <c>Equals</c>.</summary>
    public string Eq(bool value) => value ? IsTrue() : IsFalse();

    /// <summary>Field is checked/true.</summary>
    public string IsTrue() => Field() + "=TRUE()";

    /// <summary>Field is unchecked/false.</summary>
    public string IsFalse() => Field() + "=FALSE()";
}
