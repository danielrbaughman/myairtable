namespace MyAirtable;

/// <summary>An Airtable collaborator (user). Construct for writes with just an <see cref="Id"/>.</summary>
public sealed record AirtableCollaborator
{
    public string? Id { get; init; }
    public string? Email { get; init; }
    public string? Name { get; init; }
    public string? ProfilePicUrl { get; init; }
}
