namespace MyAirtable;

/// <summary>A computed-field error value (e.g. <c>{"error": "#ERROR!"}</c>).</summary>
public sealed record ErrorValue(string Error);
