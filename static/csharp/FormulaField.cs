namespace MyAirtable;

/// <summary>Base class for all formula field builders: field reference + empty/not-empty checks.</summary>
public abstract class FormulaField
{
    protected FormulaField(string fieldId) => FieldId = fieldId;

    public string FieldId { get; }

    /// <summary>Airtable field reference: <c>{fieldId}</c>.</summary>
    public string Field() => "{" + FieldId + "}";

    /// <summary>Field is blank.</summary>
    public virtual string Empty() => Field() + "=BLANK()";

    /// <summary>Field is not blank.</summary>
    public virtual string NotEmpty() => Field() + "!=BLANK()";
}
