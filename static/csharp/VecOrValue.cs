namespace MyAirtable;

/// <summary>
/// A lookup/rollup field whose cardinality (single value vs. list) can't be determined from
/// Airtable metadata alone. An abstract record with nested sealed-record cases. Name-parity
/// with the Rust/Swift/Kotlin/Java <c>VecOrValue</c>.
/// </summary>
public abstract record VecOrValue<T>
{
    private VecOrValue() { }

    public sealed record Single(T? Value) : VecOrValue<T>;

    public sealed record Multiple(List<T?> Values) : VecOrValue<T>;

    /// <summary>Flatten to a list regardless of single/multiple shape.</summary>
    public IReadOnlyList<T?> AsList() =>
        this switch
        {
            Single s => s.Value is null ? Array.Empty<T?>() : new[] { s.Value },
            Multiple m => (IReadOnlyList<T?>)(m.Values ?? new List<T?>()),
            _ => Array.Empty<T?>(),
        };
}

/// <summary>Static helpers for <see cref="VecOrValue{T}"/> (non-generic companion).</summary>
public static class VecOrValue
{
    /// <summary>
    /// Flatten a computed lookup/rollup field to its present, non-special, non-error values
    /// (Java <c>VecOrValue.cleanValues</c> parity).
    /// </summary>
    public static List<T> CleanValues<T>(VecOrValue<MaybeSpecialOrError<T>>? field)
    {
        var clean = new List<T>();
        if (field is null)
            return clean;
        foreach (var entry in field.AsList())
        {
            if (entry is MaybeSpecialOrError<T>.Value { Content: { } content })
                clean.Add(content);
        }
        return clean;
    }
}
