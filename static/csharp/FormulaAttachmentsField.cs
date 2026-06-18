namespace MyAirtable;

/// <summary>Formula builder for attachment fields.</summary>
public sealed class FormulaAttachmentsField : FormulaField
{
    public FormulaAttachmentsField(string fieldId)
        : base(fieldId) { }

    /// <summary>Has exactly N attachments.</summary>
    public string Count(int n) => "LEN(" + Field() + ")=" + n;

    /// <summary>Has no attachments.</summary>
    public override string Empty() => "LEN(" + Field() + ")=0";

    /// <summary>Has attachments.</summary>
    public override string NotEmpty() => "LEN(" + Field() + ")>0";
}
