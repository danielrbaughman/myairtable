namespace MyAirtable;

/// <summary>Formula builder for multi-select fields.</summary>
public sealed class FormulaMultiSelectField : FormulaTextOps
{
    public FormulaMultiSelectField(string fieldId)
        : base(fieldId) { }
}
