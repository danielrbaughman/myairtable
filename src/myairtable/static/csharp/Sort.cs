namespace MyAirtable;

/// <summary>A sort spec for a list query: a field (name or id) and a direction.</summary>
public sealed record Sort(string Field, SortDirection Direction = SortDirection.Asc);

/// <summary>Sort direction; wire values are <c>asc</c> / <c>desc</c>.</summary>
public enum SortDirection
{
    Asc,
    Desc,
}

public static class SortDirectionExtensions
{
    /// <summary>The Airtable wire value (<c>asc</c> / <c>desc</c>) for a sort direction.</summary>
    public static string Wire(this SortDirection direction) =>
        direction == SortDirection.Desc ? "desc" : "asc";
}
