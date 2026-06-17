namespace MyAirtable;

/// <summary>Formula builder for text fields.</summary>
public sealed class FormulaTextField : FormulaTextOps
{
    public FormulaTextField(string fieldId)
        : base(fieldId) { }
}
