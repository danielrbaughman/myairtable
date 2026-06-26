using System;

namespace MyAirtable;

/// <summary>The Airtable REST envelope for one record: id, createdTime, and typed fields.</summary>
public sealed record AirtableRecord<T>(string Id, DateTimeOffset CreatedTime, T Fields);
