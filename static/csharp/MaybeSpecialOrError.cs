namespace MyAirtable;

/// <summary>
/// A computed field that may carry a value, an Airtable special number (NaN/Infinity), or an
/// error sentinel. An abstract record with nested sealed-record cases — pattern-match with
/// <c>switch</c>. Cardinality parity with the Rust/Swift/Kotlin/Java targets.
/// </summary>
public abstract record MaybeSpecialOrError<T>
{
    private MaybeSpecialOrError() { }

    public sealed record Value(T? Content) : MaybeSpecialOrError<T>;

    public sealed record Special(SpecialNumber Number) : MaybeSpecialOrError<T>;

    public sealed record Error(ErrorValue Err) : MaybeSpecialOrError<T>;

    /// <summary>
    /// DX accessor: the wrapped value, or <c>default</c> when this is a special/error.
    /// Named <c>ValueOrDefault</c> (not <c>Value</c>) because a property cannot share the
    /// name of the nested <see cref="Value"/> case.
    /// </summary>
    public T? ValueOrDefault => this is Value v ? v.Content : default;
}
