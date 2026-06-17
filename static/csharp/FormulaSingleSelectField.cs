namespace MyAirtable;

/// <summary>Formula builder for single-select fields.</summary>
public sealed class FormulaSingleSelectField : FormulaTextOps
{
    public FormulaSingleSelectField(string fieldId)
        : base(fieldId) { }
}
