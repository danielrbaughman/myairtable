namespace MyAirtable;

/// <summary>
/// An Airtable AI text field value: the generated text and where its generation stands.
/// <see cref="State"/> is <c>empty</c>, <c>loading</c>, <c>generated</c> or <c>error</c>;
/// <see cref="ErrorType"/> is set only for <c>error</c>.
/// </summary>
public sealed record AirtableAiText(string? State, bool? IsStale, string? Value, string? ErrorType);
