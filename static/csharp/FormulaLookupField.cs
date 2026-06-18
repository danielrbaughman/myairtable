namespace MyAirtable;

/// <summary>
/// Formula builder for <c>multipleLookupValues</c> / lookup fields.
///
/// <para>Lookup field values are arrays. Airtable does not auto-coerce arrays through LOWER / TRIM /
/// FIND, so Contains/StartsWith/EndsWith would silently match nothing. <see cref="StringField"/>
/// wraps the reference in <c>ARRAYJOIN(field, ", ")</c> so string ops see a string. Equality (=) is
/// unaffected — Airtable coerces array fields to a comma-joined string under =.</para>
/// </summary>
public sealed class FormulaLookupField : FormulaTextOps
{
    public FormulaLookupField(string fieldId)
        : base(fieldId) { }

    protected override string StringField() => "ARRAYJOIN(" + Field() + ", \", \")";
}
