namespace MyAirtable;

/// <summary>Formula builder for record IDs.</summary>
public sealed class FormulaId
{
    /// <summary>Match a specific record ID.</summary>
    public string Eq(string id) => "RECORD_ID()='" + Formulas.EscapeFormulaStringSingle(id) + "'";

    /// <summary>Match any of the given record IDs.</summary>
    public string InList(IReadOnlyList<string> ids) =>
        ids.Count switch
        {
            0 => "FALSE()",
            1 => Eq(ids[0]),
            _ => Formulas.Or(ids.Select(Eq)),
        };
}
