namespace MyAirtable;

/// <summary>
/// An immutable list-query spec (filterByFormula, sort, fields, paging, view, ...). Build
/// fluently with the <c>With*</c> methods (each returns a new instance):
/// <code>new AirtableQuery().WithFormula("...").WithMaxRecords(10).WithSort("Name", SortDirection.Desc)</code>
/// </summary>
public sealed record AirtableQuery
{
    public string? Formula { get; init; }
    public IReadOnlyList<Sort> Sorts { get; init; } = Array.Empty<Sort>();
    public IReadOnlyList<string> Fields { get; init; } = Array.Empty<string>();
    public int? MaxRecords { get; init; }
    public int? PageSize { get; init; }
    public string? View { get; init; }

    /// <summary>Return cell data keyed by field id (the generated models decode by field id).</summary>
    public bool ReturnFieldsByFieldId { get; init; } = true;
    public CellFormat Format { get; init; } = CellFormat.Json;
    public string? TimeZone { get; init; }
    public string? UserLocale { get; init; }

    public AirtableQuery WithFormula(string formula) => this with { Formula = formula };

    public AirtableQuery WithFields(params string[] fields) => this with { Fields = fields };

    public AirtableQuery WithFields(IEnumerable<string> fields) =>
        this with
        {
            Fields = fields.ToArray(),
        };

    public AirtableQuery WithSort(string field, SortDirection direction = SortDirection.Asc) =>
        this with
        {
            Sorts = Sorts.Append(new Sort(field, direction)).ToArray(),
        };

    public AirtableQuery WithMaxRecords(int maxRecords) => this with { MaxRecords = maxRecords };

    public AirtableQuery WithPageSize(int pageSize) => this with { PageSize = pageSize };

    public AirtableQuery WithView(string view) => this with { View = view };

    /// <summary>Prefer a generated <c>{Table}View</c> enum over a raw id string.</summary>
    public AirtableQuery WithView(IAirtableView view) => this with { View = view.Id };

    public AirtableQuery WithReturnFieldsByFieldId(bool value) =>
        this with
        {
            ReturnFieldsByFieldId = value,
        };

    /// <summary>Flatten to ordered query parameters (un-encoded; the client URL-encodes each).</summary>
    public List<KeyValuePair<string, string>> ToParameters()
    {
        var p = new List<KeyValuePair<string, string>>();
        if (!string.IsNullOrEmpty(Formula))
            p.Add(new("filterByFormula", Formula));
        foreach (var field in Fields)
            p.Add(new("fields[]", field));
        for (var i = 0; i < Sorts.Count; i++)
        {
            p.Add(new($"sort[{i}][field]", Sorts[i].Field));
            p.Add(new($"sort[{i}][direction]", Sorts[i].Direction.Wire()));
        }
        if (MaxRecords is { } mr)
            p.Add(new("maxRecords", mr.ToString()));
        if (PageSize is { } ps)
            p.Add(new("pageSize", ps.ToString()));
        if (!string.IsNullOrEmpty(View))
            p.Add(new("view", View));
        if (ReturnFieldsByFieldId)
            p.Add(new("returnFieldsByFieldId", "true"));
        if (Format != CellFormat.Json)
            p.Add(new("cellFormat", Format.Wire()));
        if (!string.IsNullOrEmpty(TimeZone))
            p.Add(new("timeZone", TimeZone));
        if (!string.IsNullOrEmpty(UserLocale))
            p.Add(new("userLocale", UserLocale));
        return p;
    }

    public enum CellFormat
    {
        Json,
        String,
    }
}

internal static class CellFormatExtensions
{
    public static string Wire(this AirtableQuery.CellFormat format) =>
        format == AirtableQuery.CellFormat.String ? "string" : "json";
}
