# C# Language Support — Implementation Plan v2

> **Changes from v1 (plan-critic round, 2026-06-16)**: enumerated the transpiler integration
> precisely — the `_emit_function_call` guard at formula_transpiler.py:498 must gain `"csharp"`
> or every runtime function call dispatches wrong (CRIT-1); the `map_types()` idempotency guard
> (:218-221) must also check `_csharp_type` to avoid stale types on cached runs (CRIT-2); added
> explicit C# arms with PascalCase + `JsonNode` boxing for `_emit_fn_record_id`, `_emit_fn_not/
and/or/xor`, `_emit_fn_blank`(arg), and the `_emit_binary_op` equality group (`JsonNode.DeepEquals`)
> (CRIT-4/CRIT-5/HIGH-2/HIGH-4/MED-1); removed `computed_union_fmt` from the C# `LanguageConfig`
> so wrapping happens ONLY via `apply_csharp_computed_wrapping()` (HIGH-3/MED-8 — double-wrap
> would not compile); committed to a generated per-enum `JsonConverter<T>` (dropped the
> `[EnumMember]`/`JsonStringEnumConverter` alternatives — .NET 8 lacks `[JsonStringEnumMemberName]`,
> MED-4); mandated `field_name_map` populated with `name_pascal()` for C# so evaluate methods emit
> `this.MyField` not `this.myField` (MED-6); concretized the xUnit ordering story
> (`IClassFixture` + `[TestCaseOrderer]` + `PriorityOrderer`, **xUnit v2**, assembly-attribute
> parallelization-off, HIGH-6/R-new-3); specified the C# `SWITCH` runtime signature (MED-2);
> `V()` must short-circuit on `JsonNode` to avoid double-serialization (R-new-1); F1.13(b) now
> probes `VecOrValue<DateTimeOffset>` and null-valued computed decode (HIGH-5/R-new-2); both
> `make_test_base` call sites get `_csharp_type` (LOW-1); XML-doc escaping incl. `--` (LOW-6);
> `IAsyncEnumerable` pagination declared a non-goal (LOW-5).
>
> **Cross-language refinements (2026-06-16, after comparing ALL eight targets, not just Java)**:
> the error hierarchy gains the missing **`NetworkError`** variant — Swift/Kotlin/Java all carry
> **7** variants and v1/early-v2 had 6 (§2.3.7); the sum types `VecOrValue<T>`/`MaybeSpecialOrError<T>`
> become **`abstract record` + nested `sealed record` cases** (pattern-matchable), matching the
> Rust/Swift enum + Kotlin sealed-interface + Java sealed-record spirit rather than a Java-style
> abstract-class hierarchy (§2.3.4); the async client/cache adopt **`SemaphoreSlim`** (async-aware,
> Kotlin-`Mutex` analog) over a `lock`, with split-lock check-fetch-store, **exponential backoff +
> jitter** and **429 _and_ 5xx** retry (Kotlin/Java), `Task.Delay` honoring `CancellationToken`
> (§2.3.8); immutable value carriers (Attachment/Collaborator/Button/Record/Sort) become `record`s
> with `init` props while ORM **models stay mutable classes** (dirty-tracking needs settable props,
> §2.3.1/§2.4). Two deliberate retentions vs the comparison agents' suggestions: ALL coercion
> helpers stay on `AirtableRuntime` (single `_runtime` transpiler qualifier — splitting onto
> `AirtableJson` would break it, §2.3.3); the value type stays `JsonNode` not `JsonElement` (the
> latter is a read-only view bound to a `JsonDocument`, not the constructable mutable DOM the runtime
> needs, §2.3.3). Filter `Eq`/`Neq` confirmed (object.Equals footgun is C#-real, unlike Swift/Rust/TS).

## 1. Overview & Goals

Add full-parity **C#** code generation to `myairtable` — the ninth target, alongside Python,
TypeScript, JavaScript, Rust, Swift, Kotlin, Java, and Go. The closest template is the **Java**
target (epic `myairtable-kree`): same one-public-type-per-file discipline, same boxed-JSON-node
runtime value, same sum-type wrapper strategy, same test-base semantics. But the generated code
must feel **idiomatic modern C# (.NET 8 / C# 12)** — not Java-with-properties: async/await `Task`
methods, auto-properties with object-initializer construction, `System.Text.Json` with custom
converters, `DateTimeOffset`/`TimeSpan`, a single file-scoped `namespace`, an exception hierarchy
(all unchecked in C#), `@`-verbatim keyword escaping.

**Scope:**

- Generator at `src/generators/csharp.py` + `src/utils/write_to_csharp_file.py`
- Static runtime at `static/csharp/` (custom Airtable client — `HttpClient` + `System.Text.Json`;
  no third-party Airtable SDK)
- Type mapping (`GENERIC_TO_CSHARP`) + formula transpiler C# emitter
- Unit tests: `tests/test_generators.py` C# classes, `tests/test_formula_transpiler_csharp.py`,
  `tests/csharp_static/` xUnit test project (16 test files, Java parity)
- Integration tests at `myairtable-tests/csharp/` (parity with Java/Kotlin/Swift/Rust/TS)
- CLI wiring (`main.py csharp` + `all --csharp-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):** NuGet packaging / `.nupkg` emission; **Native AOT / source-generated
serialization** (the reflection-based generic `JsonConverterFactory` for the sum types is not
trim-safe — explicit non-goal, §2.3.4); `netstandard2.0` multi-targeting; synchronous API variants;
`IAsyncEnumerable<T>` streaming pagination (list endpoints return `Task<List<…>>` like every other
target — streaming is a future enhancement); F#/VB consumption concerns; `.sln` emission.

## 2. Design Decisions

### 2.1 User-approved (2026-06-16)

| #   | Question       | Answer                                                    |
| --- | -------------- | --------------------------------------------------------- |
| 1   | Async model    | **async/await `Task`/`Task<T>`** + `CancellationToken`    |
| 2   | Target FW      | **.NET 8 (LTS)** — `net8.0`, C# 12, nullable refs enabled |
| 3   | JSON library   | **System.Text.Json** (custom `JsonConverter`s for sums)   |
| 4   | Test framework | **xUnit v2** (unit + integration)                         |

Build tooling: **.NET SDK / MSBuild**, hand-written `.csproj` in consuming projects (generator
emits no project/build files — parity with all other targets). HTTP via a shared `HttpClient`.

### 2.2 Java-pattern → C# idiom mapping

| Java construct                                                     | C# equivalent                                                                                                                                                                                            |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `final class AirtableClient` + JDK HttpClient + `ReentrantLock`    | `sealed class AirtableClient` + shared `HttpClient` + `lock`/`SemaphoreSlim`; **async** methods                                                                                                          |
| Mutable POJO + no-arg ctor + Jackson field-access                  | Mutable class + **public parameterless ctor** + auto-properties; STJ property-based decode (§2.3.1)                                                                                                      |
| Jackson `JsonNode` (type-erased value)                             | `System.Text.Json.Nodes.JsonNode` (mutable DOM). **JSON null = C# `null` JsonNode, no `NullNode` sentinel** (§2.3.3)                                                                                     |
| `sealed interface VecOrValue<T>` + ContextualDeserializer          | **`abstract record VecOrValue<T>`** + nested **`sealed record`** `Single`/`Multiple` (pattern-matchable, Rust/Swift/Kotlin spirit) + **generic `JsonConverterFactory`** registered **globally** (§2.3.4) |
| `sealed interface MaybeSpecialOrError<T>`                          | **`abstract record MaybeSpecialOrError<T>`** + nested **`sealed record`** `Value`/`Special`/`Error` + factory converter                                                                                  |
| `enum` + `@JsonValue`/`@JsonCreator`                               | `enum` + **generated per-enum `JsonConverter<T>`** keyed on raw Airtable strings (§2.4, MED-4)                                                                                                           |
| `sealed abstract class AirtableException extends RuntimeException` | `abstract class AirtableException : Exception` + sealed subclasses; C# exceptions all unchecked (§2.3.7)                                                                                                 |
| Plain blocking method                                              | `async Task<T> …Async(…, CancellationToken)`                                                                                                                                                             |
| `final class AirtableRuntime` static methods                       | `static class AirtableRuntime` — owns ALL coercions V/N/S/A/AN/AS/D/IsTruthy + ~80 functions (§2.3.3)                                                                                                    |
| `public static final f` filter accessor                            | `public static readonly PrimaryFilters F` → `PrimaryModel.F.PrimaryKey.Eq(...)`                                                                                                                          |
| `_java_ident()` `_`-suffix rename (no escape in Java)              | **`@`-verbatim identifier** (`@class`, `@event`) — C# HAS an escape mechanism (§2.3.5)                                                                                                                   |
| `java.time.Instant` + custom serializer                            | `DateTimeOffset` + custom converter (3-format decode)                                                                                                                                                    |
| `java.time.Duration`, wire = numeric seconds                       | `TimeSpan` + custom converter, wire = **numeric seconds** (§2.3.6)                                                                                                                                       |
| Generated nested `Builder` (writable fields)                       | **Object-initializer** `new PrimaryModel { PrimaryKey = "x" }` — no builder, no Create class (§2.3.11)                                                                                                   |
| Per-model fluent `save()/fetch()/delete()` (no reified generics)   | Per-model `SaveAsync()/FetchAsync()/DeleteAsync()` covariant returns → `ModelOps` (C# generics ARE reified — §2.3.12)                                                                                    |

### 2.3 C#-specific decisions

#### 2.3.1 Model shape: mutable class + parameterless ctor + auto-properties

```csharp
public sealed class PrimaryModel : AirtableModel {
    /// <summary>Single Line Text <c>fldXXX</c></summary>
    [JsonPropertyName("fldXXX")]
    public string? SingleLineText { get; set; }            // writable: get + set

    /// <summary>Auto Number <c>fldYYY</c> — read-only</summary>
    [JsonPropertyName("fldYYY")]
    [JsonInclude]
    public MaybeSpecialOrError<long>? AutoNumber { get; private set; }   // computed: get + private set

    public PrimaryModel() {}                               // STJ uses this; object-initializer entry
}
```

- **STJ instantiation contract**: System.Text.Json instantiates via the **public parameterless
  constructor** and assigns settable properties. Every generated model emits `public {Table}Model()`.
- **Writable** fields: `{ get; set; }` (settable via object initializer = creation idiom, §2.3.11).
- **Computed** fields: `[JsonInclude] public T? Name { get; private set; }` — STJ honors `[JsonInclude]`
  on non-public setters (.NET 7+). User cannot mutate; object-initializer creation omits them. The
  global `DefaultIgnoreCondition = WhenWritingNull` only affects _encoding_ — a null computed value
  from Airtable still decodes through the private setter (proven in F1.13(b), HIGH-5).
- `[JsonPropertyName(...)]` raw values are **field IDs**.
- Create/update payloads are **hand-rolled** (`ToCreateFields()` / `DirtyFields()` returning
  `JsonObject` over writable field IDs only). Shared options decode wholesale only.
- Dirty tracking: `[JsonIgnore] private Dictionary<string, JsonNode?> _snapshot` + diff.
- Numbers are nullable value types (`double?`, `long?`, `bool?`) so absent ≠ default-zero.

#### 2.3.2 Filter DSL uses `Eq` / `Neq`

C# has the same footgun as Java/Kotlin: `Equals(object)` exists on every type, so a generated
`Equals(string)` overload would shadow `object.Equals`. Keep **`Eq`/`Neq`** (PascalCase); all other
names match the other languages (`Contains`, `StartsWith`, `GreaterThan`, `IsEmpty`/`IsNotEmpty`, …).
Accessor: `public static readonly PrimaryFilters F = new();` → `PrimaryModel.F.PrimaryKey.Eq("x")`.

#### 2.3.3 `JsonNode` is the type-erased value; ALL coercions on `AirtableRuntime`; JSON-null = C# null

The formula runtime operates on `System.Text.Json.Nodes.JsonNode?`. Every coercion helper —
`V`, `N`, `S`, `A`, `AN`, `AS`, `D`, `IsTruthy` — is a **static method on `AirtableRuntime`**, so the
transpiler's single `_runtime = "AirtableRuntime"` qualifier covers all of them (Java model).

**Critical C# divergence from Java**: System.Text.Json represents a JSON `null` as a C# `null`
`JsonNode` reference — there is **no `NullNode` sentinel** (unlike Jackson). So:

- `V(null)` returns `null`; the runtime/`IsTruthy` treats `null` JsonNode as **BLANK**.
- The transpiler emits the bare `null` literal where Java emits `NullNode.getInstance()`.
- Number/string/bool literals use `JsonValue.Create(value)`.
  **Why `JsonNode` and not `JsonElement`**: `JsonElement` is a read-only struct that is a _view_ into a
  `JsonDocument`'s pooled buffer (lifetime-bound, not freely constructable). The formula runtime must
  _build_ values (`JsonValue.Create(...)`, assemble arrays/objects) and pass them around freely, so it
  needs the **mutable DOM** — `JsonNode`/`JsonObject`/`JsonArray`/`JsonValue`.

**Why ALL coercions live on `AirtableRuntime`** (not split onto `AirtableJson` à la Kotlin): the
transpiler emits a single `_runtime` qualifier; consolidating `V/N/S/A/AN/AS/D/IsTruthy` on one static
class lets `AirtableRuntime.X(...)` cover every coercion (Java's MED-16 decision). `AirtableJson`
owns ONLY the shared `JsonSerializerOptions`.

- **`V()` must short-circuit on `JsonNode`** to avoid double-serialization (R-new-1):

```csharp
public static JsonNode? V(object? value) =>
    value switch {
        null => null,
        JsonNode node => node,
        _ => JsonSerializer.SerializeToNode(value, AirtableJson.Options),
    };
```

- **Structural equality** uses `JsonNode.DeepEquals(a, b)` (.NET 6+), wrapped in an
  `AirtableRuntime.IsEqual(JsonNode? a, JsonNode? b)` helper that coerces through `N()`/`S()` for
  cross-type number/string comparison and falls back to `DeepEquals` — `==` on `JsonNode` is
  reference equality and must never be emitted for value comparison (HIGH-2/MED-7).

#### 2.3.4 Sum types as records; generic converters via `JsonConverterFactory`, registered globally (CRIT)

**Shape** (cross-language: Rust/Swift use enums, Kotlin sealed interfaces, Java sealed records — the
idiomatic C# analog is `abstract record` + nested `sealed record` cases, giving exhaustive pattern
matching and free value-equality/`with`-expressions):

```csharp
public abstract record VecOrValue<T> {
    public sealed record Single(T? Value) : VecOrValue<T>;
    public sealed record Multiple(List<T?> Values) : VecOrValue<T>;
    // DX: T? Value (Single only) / IReadOnlyList<T?> Values / static CleanValues(...) parity w/ Java
}
public abstract record MaybeSpecialOrError<T> {
    public sealed record Value(T? Content)        : MaybeSpecialOrError<T>;
    public sealed record Special(SpecialNumber N) : MaybeSpecialOrError<T>;
    public sealed record Error(ErrorValue E)      : MaybeSpecialOrError<T>;
    public T? Value => this is Value v ? v.Content : default;   // DX accessor (null unless Value)
}
```

System.Text.Json's analog of Java's `ContextualDeserializer` is a **`JsonConverterFactory`**:

- `VecOrValueConverterFactory.CanConvert(t)` → `t.IsGenericType && t.GetGenericTypeDefinition() == typeof(VecOrValue<>)`.
- `CreateConverter` reflects the element type and instantiates `VecOrValueConverter<T>` via
  `Activator.CreateInstance(typeof(VecOrValueConverter<>).MakeGenericType(elem))`.
- `VecOrValueConverter<T>.Read` peeks (`reader.TokenType == JsonTokenType.StartArray` →
  `Multiple(List<T>)`, else `Single(T)`), delegating element (de)serialization **through
  `options`** (`JsonSerializer.Deserialize<T>(ref reader, options)`) so nested
  `VecOrValue<MaybeSpecialOrError<T>>` resolves via the registered `MaybeSpecialOrError<>` factory.
- `MaybeSpecialOrError<T>`: object with `"specialValue"` → `Special`; object with `"error"` →
  `Error`; else deserialize to `T` → `Value`.

**Registration is GLOBAL** (both factories added once to `AirtableJson.Options`) — _cleaner than
Java's field-level annotations_. The generator emits **no** per-field converter attributes.

**F1.13 prototype gate** must prove, using **only options-level registration** (no field attributes):
round-trips (decode AND encode) for `MaybeSpecialOrError<string>`, `<double>`, `<DateTimeOffset>`,
`VecOrValue<string>`, **`VecOrValue<DateTimeOffset>`** (probes the factory→custom-date-converter chain,
R-new-2), the nested `VecOrValue<MaybeSpecialOrError<string>>`, **and a null-valued computed field**
decoding correctly despite `DefaultIgnoreCondition=WhenWritingNull` (HIGH-5). This is the single
riskiest C# foundation.

#### 2.3.5 Single namespace `MyAirtable`; one public type per file; `@`-verbatim keyword escape

All files declare a file-scoped `namespace MyAirtable;`. **C# decouples namespace from directory**
(unlike Go/Java packages), so the Models/Options/Types/Formulas/Tables folder split is purely
organizational — **no package-vs-directory compile gate is needed** (a genuine simplification over
the Java/Go plans). One public type per file by convention; tightly coupled helpers nest.

**Keyword escaping**: `_csharp_ident()` prefixes reserved words with `@` (verbatim identifier —
`@class`, `@event`), keeping the logical name (vs Java's `_`-suffix rename). Invisible in JSON
(field IDs come from `[JsonPropertyName]`). Reserved set = C# reserved keywords; contextual keywords
(`value`, `async`, `await`, `record`, …) escaped defensively where they appear as identifiers.

#### 2.3.6 Date / Duration / numbers

- `DateTimeOffset` for datetimes (idiomatic absolute timestamp ≈ Java `Instant`). Custom converter
  decode order: ISO-8601-with-offset → ISO-8601 (assume UTC) → date-only `YYYY-MM-DD` (→ midnight
  UTC). Encode ISO-8601. (Alternative `DateTime` (Utc kind) noted; `DateTimeOffset` chosen for offset
  fidelity — flagged for user review.)
- Duration → `TimeSpan`, wire = **numeric seconds** (locked by Swift/Kotlin live verification).
  **Risk**: STJ's built-in `TimeSpan` converter emits string `"00:00:30"` — the custom converter MUST
  read/write numeric seconds (`TimeSpan.FromSeconds` / `.TotalSeconds`). F1.13(c) asserts.
- Airtable `number` fields are ALWAYS `double` — tests use `42.0`. `autoNumber`/`count` map to `long`.
- **`Math.Exp(1.0)` ULP check**: verify .NET vs V8/Airtable `Math.E`; if it differs by a ULP (as JVM
  does), port the pinned `EXP(1.0) == Math.E` special case. Verify-first in the runtime task.

#### 2.3.7 Errors: unchecked exception hierarchy

`public abstract class AirtableException : Exception` with **7** sealed subclasses (the canonical set
Swift/Kotlin/Java all carry — cross-language audit caught that an early draft had only 6):
`HttpError(status, body)`, `ApiError(code, message)`, `DecodingError(inner)`, `InvalidUrlError`,
`MissingCredentialsError`, **`NetworkError(inner)`** (transport-level failure — NOT a 429; the client
throws this on `HttpRequestException` with no response), `RateLimitedError(retryAfterSeconds)`. All C#
exceptions unchecked. Pattern-matching `switch` works in tests. Subclasses use the `Error` suffix .NET
analyzers expect. `TestAirtableExceptionDecoding.cs` covers all 7 (Rust's runtime has a smaller set —
parity target is the Swift/Kotlin/Java 7).

#### 2.3.8 Concurrency (async — Swift/Kotlin reference, NOT Java's blocking model)

`sealed class AirtableClient`, async methods returning `Task`/`Task<T>` with `CancellationToken`
threaded through to `HttpClient.SendAsync`. A single shared `HttpClient` (thread-safe; avoids socket
exhaustion).

- **Cache guard**: `SemaphoreSlim(1,1)` (async-aware — the C# analog of Kotlin's coroutine `Mutex`),
  **never `lock`** (a `lock`/`Monitor` cannot be held across `await` and a blocking `lock` around async
  work risks thread-pool starvation/deadlock). Pattern: **split-lock** check-fetch-store — acquire,
  check TTL/LRU, _release_, `await` the HTTP fetch unlocked, re-acquire to store (Rust/Java do the same
  split; Kotlin holds across the await, Swift's actor serializes — split is the safe C# default and
  avoids serializing unrelated reads behind one in-flight fetch). Per-table `Invalidate(tableId)` +
  `InvalidateAll()`.
- **Retry/backoff**: retry on **HTTP 429 _and_ 5xx** (matches Swift's retryable check), `await
Task.Delay(delay, ct)` (never `Thread.Sleep`), delay = `Retry-After` header ?? exponential
  `baseDelay * 2^attempt`, **plus decorrelation jitter** (Kotlin/Java add it; Swift omits it — jitter
  is the right call for a multi-client library to avoid stampedes). `OperationCanceledException`
  propagates (honor cancellation); transport failures → `NetworkError`.
- **Pagination**: eager — list endpoints accumulate and return `Task<List<…>>` (parity with
  Swift/Kotlin/Rust/Java; none stream). `IAsyncEnumerable<T>` streaming is a declared non-goal (§1).

#### 2.3.9 URL encoding verify-first

.NET `Uri.EscapeDataString("+")` → `%2B` (likely correct — opposite of the Ktor/Swift raw-`+` bug).
**Verify-first spike**: confirm a `filterByFormula` of `LEN({field})+1` round-trips against the real
base (build query per value with `Uri.EscapeDataString`, never a helper that turns space→`+`). Path
segments (table names) also use `Uri.EscapeDataString`. Pinned by `TestClientUrlEncoding.cs`.

#### 2.3.10 Formatter & lint

**CSharpier** (opinionated reflow formatter; `dotnet tool install -g csharpier`) with
`command -v csharpier` warn-skip guards in BOTH repos' checks.sh. Scope: `static/csharp/`,
`tests/csharp_static/`, `myairtable-tests/csharp/` — **NEVER generated output**. The generator emits
CSharpier-style output. A shared `.editorconfig` pins style. (`dotnet format` is the SDK fallback but
only does editorconfig whitespace, not reflow.)

#### 2.3.11 Creation idiom: object initializer (no builder)

`new PrimaryModel { PrimaryKey = "x" }` — nicer than Java's builder, zero generated ceremony (writable
props are `{ get; set; }`). No builder, no separate `Create{Table}` type. Plain setters cover
post-fetch mutation (`model.Email = …;` before `SaveAsync()`).

#### 2.3.12 Model DX surface: `AirtableModel` base + per-model fluent async methods

`AirtableModel` is an **abstract base class** (cleaner than Java's interface — holds shared `Id`,
`CreatedTime`, `AttachedClient`, `_snapshot`):

- Members: `Id`, `CreatedTime`, `AttachedClient`, `TakeSnapshot()`, `DirtyFields()`, `ToRecord()`,
  `ToCreateFields()`, `IsNew`; `RequireId()` / `RequireAttachedClient()`.
- C# generics are **reified**, so `ModelOps` needs no class token. Generator emits per-model fluent
  CRUD with covariant returns:
  `public Task<PrimaryModel> SaveAsync(CancellationToken ct = default) => ModelOps.SaveAsync(this, ct);`
  (likewise `FetchAsync`/`DeleteAsync`), delegating to static async `ModelOps` using `GetType()`/`<T>`.
- DX value accessors: `T? Value` on `MaybeSpecialOrError<T>`; `Values()`/`CleanValues()` on
  `VecOrValue<T>` / `VecOrValue<MaybeSpecialOrError<T>>`. Covered by `TestDxHelpers.cs`.

### 2.4 Other settled choices

| Decision            | Value                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Test framework      | **xUnit v2** (`Xunit`, `Assert.*`)                                                                                                                                                                                                                                                                                                                                                             |
| Integration phasing | New-instance-per-test → shared CRUD state via **`IClassFixture<CrudFixture>`** (constructor-injected; `IDisposable` for cleanup); ordering via custom **`PriorityOrderer : ITestCaseOrderer`** + `[TestPriority(n)]` attribute, applied with `[TestCaseOrderer("MyAirtable.Tests.PriorityOrderer", "CSharpTests")]` on the class — the analog to Java `PER_CLASS` + `@TestMethodOrder` (§ R11) |
| Test parallelism    | Cross-class parallelism OFF via **`[assembly: CollectionBehavior(DisableTestParallelization = true)]`** in `AssemblyInfo.cs` (xUnit v2 mechanism — NOT `xunit.runner.json`, which is v3); distinct primary keys per file (`"CSharp StructCrud PKOnly {ts}"`)                                                                                                                                   |
| File naming         | `PascalCase.cs` (one public type = filename); properties/methods/enum-members `PascalCase` via `name_pascal()` (NOT camelCase)                                                                                                                                                                                                                                                                 |
| Select-option enums | C# enum; member names PascalCase via `_choice_to_entry()` port; **generated per-enum `JsonConverter<{Enum}>`** mapping raw Airtable strings ↔ members (no `JsonStringEnumConverter`/`[EnumMember]` — .NET 8 lacks per-member custom names); applied via `[JsonConverter(typeof(...))]` on the enum; dedup collisions (v2/v3 suffix parity)                                                     |
| Linked records      | Raw `List<string>` record IDs; resolve via `airtable.Secondary.GetAsync(ids)`                                                                                                                                                                                                                                                                                                                  |
| Dirty tracking      | `[JsonIgnore]` snapshot dict + diff                                                                                                                                                                                                                                                                                                                                                            |
| Table accessors     | `airtable.Primary` **properties** (C# idiom — not `Primary()` methods)                                                                                                                                                                                                                                                                                                                         |
| `.csproj`           | NOT emitted by generator — hand-written in consuming projects                                                                                                                                                                                                                                                                                                                                  |
| XML doc comments    | `/// <summary>…</summary>`, `<c>fieldId</c>`, formula text in `<code>…</code>`; escape `<`→`&lt;`, `>`→`&gt;`, `&`→`&amp;`, and replace `--` (illegal inside XML comments) — unit-tested in `write_to_csharp_file.py` (LOW-6)                                                                                                                                                                  |

## 3. File Layout

### 3.1 Source repo (`myairtable`) — integration points (3 separate `Language` literals)

```
src/generators/csharp.py              # NEW ~1000-1100 LOC (mirrors java.py)
src/utils/write_to_csharp_file.py     # NEW WriteToCSharpFile (XML doc + `--` scrub, region, class/
                                      #   enum/property/method helpers, _csharp_ident() @-verbatim,
                                      #   _choice_to_entry(), _csharp_string_literal(), name_pascal())
src/utils/type_mapper.py              # MOD:
                                      #   • GENERIC_TO_CSHARP map
                                      #   • "csharp" in type_mapper Language literal (:361)
                                      #   • LanguageConfig entry: list_fmt="List<{0}>",
                                      #     union_fmt="VecOrValue<{0}>", unknown="JsonNode";
                                      #     **NO computed_union_fmt** (leave default "") — wrapping is
                                      #     done ONLY by apply_csharp_computed_wrapping() (HIGH-3)
                                      #   • map_csharp_type(); apply_csharp_computed_wrapping()
                                      #   • is_already_list csharp case (startswith "List<")
                                      #   • map_types() first-pass csharp line (after _go_type, ~:247)
                                      #   • **map_types() idempotency guard (:218-221) ALSO checks
                                      #     first_field._csharp_type is not None** (CRIT-2)
                                      #   • apply_disambiguated_type() csharp branch (~:951-958)
src/utils/write_to_file.py            # MOD: add "csharp" to language Literal (:49); add "csharp" to
                                      #   the pipe-list in header match case (:74 — // comments)
src/meta.py                           # MOD: _csharp_type PrivateAttr + csharp_type property
src/formulas/formula_transpiler.py    # MOD (enumerated below)
main.py                               # MOD: `csharp` command + `all --csharp-folder`
checks.sh                             # MOD: csharp section (csharpier guard + `dotnet test`
                                      #   tests/csharp_static; warn-skip if no dotnet)
static/csharp/                        # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestCSharp* classes; **BOTH** __pydantic_private__ sites
                                      #   (make_test_base ~:75 AND inline fixture ~:471) gain
                                      #   "_csharp_type": None (LOW-1)
tests/test_formula_transpiler_csharp.py  # NEW (mirror Java twin, ~45-50 cases) — assert FieldRef
                                      #   emits this.MyField (PascalCase, MED-6)
tests/csharp_static/                  # NEW xUnit v2 project
  ├── CSharpStatic.Tests.csproj       #   net8.0; xUnit v2; <Compile Include="../../static/csharp/**/*.cs"/>
  └── *.cs                            # 16 files = Java parity (TestPocoModel gate + 15, see §3.1 list in v1)
```

**`formula_transpiler.py` C# arms — explicit checklist (F8.1):**

1. `"csharp"` in `Language` literal (:21).
2. `_runtime` (:333): add `"csharp"` to the `("swift","kotlin","java")` tuple → `"AirtableRuntime"`.
3. `_self` (:323-328): C# falls into the existing `else → "this"` — **no change**, covered by test.
4. **`_emit_function_call` guard (:498)**: add `"csharp"` to `("swift","kotlin","java","go")` so
   runtime calls dispatch via `_rt(node.name)` (else they hit the dead `else` → wrong format). **CRIT-1 —
   load-bearing for COUNTALL/CONCATENATE/REPT/etc.**
5. `_emit_str`/`_emit_num` (:1218/:1246): C# falls through to the **qualified** default
   `AirtableRuntime.S()/N()` — **no new arm**; do NOT add a `csharp` arm to the bare-call kotlin/go guard.
6. **`_emit_fn_record_id` (:547-551)**: add C# arm → `AirtableRuntime.V(this.Id ?? "")` (PascalCase
   `Id`, null-coalesce) — else falls to bare `this.id` (CRIT-5).
7. **`_emit_fn_not` (:612)**: `AirtableRuntime.V(!AirtableRuntime.IsTruthy(arg))` (HIGH-4).
8. **`_emit_fn_and`/`_emit_fn_or` (:618-680)**: `AirtableRuntime.V(IsTruthy(a) && IsTruthy(b))` /
   `|| ` — else C# hits the `&&`-join default without `IsTruthy`+`V()` boxing (MED-1).
9. **`_emit_fn_xor` (:777)**: PascalCase `IsTruthy` + `V()` boxing arm.
10. `_emit_fn_blank` no-arg (:587): C# uses the `else → "null"` default — **intentional**, document.
11. **`_emit_fn_blank` with arg (:596)**: add C# arm → `AirtableRuntime.V((arg) == null)` (CRIT-4).
12. `_emit_fn_if`/`_emit_fn_ifs`/`_emit_fn_switch` fallback: C# fallback = bare `null`; verify C#
    reaches the `else → "null"` (NOT a java `NullNode` arm). Document to prevent a wrong arm.
13. **`_emit_fn_switch` (:869-976)**: add C# arm emitting `AirtableRuntime.SWITCH(expr, null, pat1, val1, …)`
    matching the C# runtime signature (§4, MED-2).
14. Literals (:352-389): C# arm — `JsonValue.Create(num/str/bool)`, bare `null` (§2.3.3).
15. **`_emit_binary_op` equality group (:1326-1367)**: add `"csharp"` to `("kotlin","swift","rust","java")`;
    C# arm uses `AirtableRuntime.IsEqual(...)` (DeepEquals + coercion) not `==` (HIGH-2/MED-7).
16. `_emit_binary_op` arithmetic/comparison + `_emit_unary_op`: C# arms (number wrapping via `N()`).
17. FieldRef (`_emit_field_ref` :405-443): `AirtableRuntime.V(this.MyField)` — **PascalCase** from
    `field_name_map` populated with `name_pascal()` (MED-6).
18. `_csharp_ident` escaping applied to emitted identifiers.

### 3.2 Generated output (per run)

```
csharp/output/                    # generator does NOT emit .csproj/.sln
├── dynamic/{Models,Options,Types,Formulas,Tables}/*.cs
├── static/                       # copied from static/csharp/
└── Airtable.cs
```

All files declare `namespace MyAirtable;` (no compile gate — §2.3.5).

### 3.3 Test repo (`myairtable-tests`)

```
csharp/
├── CSharpTests.csproj            # HAND-WRITTEN: net8.0; xUnit v2; <Compile Include="output/**/*.cs"/>
├── AssemblyInfo.cs               # [assembly: CollectionBehavior(DisableTestParallelization = true)]
├── output/                       # regenerated by build.sh
└── tests/
    ├── TestHarness.cs            # smoke: MyAirtableRuntimeInfo.Version
    ├── TestSetup.cs              # .env walker + Airtable factory + PrimaryKey(suite, label)
    ├── PriorityOrderer.cs        # ITestCaseOrderer + [TestPriority] (§ R11)
    ├── CrudFixture.cs            # IClassFixture state holder (created IDs), IDisposable cleanup
    ├── TestStructCrudViaTable.cs
    ├── TestOrmCrudViaTable.cs
    ├── TestOrmCrudViaModel.cs
    ├── TestSerializing.cs
    ├── TestFilterByFormula.cs
    ├── TestRuntimeFormulas.cs
    ├── TestCaching.cs
    ├── TestLinkedRecords.cs
    ├── TestComplexProperties.cs
    └── TestSpecialErrorDeser.cs   # = 10 scenario files + 4 infra (Harness/Setup/Orderer/Fixture)
build.sh                          # MOD: --csharp-folder ./csharp/output
test.sh                           # MOD: cs case + ADD cs to `for lang in ts js py rs swift kotlin java go`
checks.sh                         # MOD: csharpier (command -v guard) + `dotnet build csharp`
```

`test.sh` cs case (xUnit `dotnet test --filter`):

```bash
elif [ "$LANG_ARG" = "cs" ]; then
    case "$SUITE" in
        --all)     TEST_CMD="(cd csharp && dotnet test)" ;;
        --crud)    TEST_CMD="(cd csharp && dotnet test --filter 'FullyQualifiedName~TestStructCrudViaTable|FullyQualifiedName~TestOrmCrudViaTable|FullyQualifiedName~TestOrmCrudViaModel')" ;;
        --json)    TEST_CMD="(cd csharp && dotnet test --filter 'FullyQualifiedName~TestSerializing')" ;;
        --filter)  TEST_CMD="(cd csharp && dotnet test --filter 'FullyQualifiedName~TestFilterByFormula')" ;;
        --runtime) TEST_CMD="(cd csharp && dotnet test --filter 'FullyQualifiedName~TestRuntimeFormulas')" ;;
        --cache)   TEST_CMD="(cd csharp && dotnet test --filter 'FullyQualifiedName~TestCaching')" ;;
    esac
```

## 4. Static Runtime Contract (static/csharp/, ~32-38 files)

One public type per file. Same inventory as v1 §4, with these clarified signatures:

- `AirtableRuntime.cs`: `static class`; ALL coercions `V/N/S/A/AN/AS/D/IsTruthy` (PascalCase) +
  `IsEqual(JsonNode?, JsonNode?)` (DeepEquals + N/S coercion) + ~80 functions. `V()` short-circuits
  on `JsonNode` (§2.3.3). `SWITCH` signature:
  `public static JsonNode? SWITCH(JsonNode? expr, JsonNode? @default, params JsonNode?[] flatPairs)`
  (flat varargs, Java/Go shape). EXP(1.0) ULP pin per §2.3.6.
- `AirtableJson.cs`: shared `JsonSerializerOptions` (PropertyNameCaseInsensitive,
  `DefaultIgnoreCondition = WhenWritingNull`, `VecOrValueConverterFactory` +
  `MaybeSpecialOrErrorConverterFactory` + `AirtableDateConverter` + `AirtableDurationConverter`
  registered).
- `VecOrValue.cs` / `MaybeSpecialOrError.cs`: **`abstract record`** + nested **`sealed record`** cases
  - DX accessors (§2.3.4). `VecOrValueConverter.cs` / `MaybeSpecialOrErrorConverter.cs`:
    `JsonConverterFactory` + generic `Converter<T>` delegating element (de)serialization through `options`.
- `AirtableException.cs`: abstract base + **7** sealed subclasses incl. `NetworkError` (§2.3.7).
- `CacheStore.cs`: TTL + LRU behind **`SemaphoreSlim`** (async-aware); split-lock check-fetch-store;
  per-table `Invalidate` + `InvalidateAll` (§2.3.8).
- `AirtableClient.cs`: shared `HttpClient`, async endpoints, **429+5xx** retry via `Task.Delay` +
  jitter honoring `CancellationToken`, owns `CacheStore`, chunk-of-10 batching; query/path encoding via
  `Uri.EscapeDataString` (§2.3.9); transport failures → `NetworkError`.
- **Immutable value carriers as `record`s with `init` props** (Swift/Kotlin spirit): `AirtableRecord`,
  `AirtableAttachment` (+ nested `Thumbnails`/`Thumbnail`), `AirtableCollaborator`, `AirtableButton`,
  `Sort` (+ `SortDirection` enum), `SpecialNumber`, `ErrorValue`. (ORM **models** are NOT records —
  mutable classes for dirty tracking, §2.3.1.)
- (Remaining files: `AirtableModel` (abstract class), `ModelOps`, `AirtableQuery`, `IAirtableView`,
  `Fields`, `DictTable`, `OrmTable`, `Formulas` + field classes, `MyAirtableRuntimeInfo` — as v1 §4.)

## 5. Feature Breakdown (→ beads epic/features/tasks)

Same 11-feature structure as v1, with these v2 amendments folded into the named tasks:

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `write_to_file.py`: `"csharp"` in Literal (:49) + header pipe-list (:74).
- 1.2 `write_to_csharp_file.py` (`@`-verbatim `_csharp_ident()`, `name_pascal()`, `_choice_to_entry()`,
  `_csharp_string_literal()`, XML-doc escaping incl. `--` scrub + escape tests).
- 1.3 Type wiring — GENERIC_TO_CSHARP; type_mapper Language literal; LanguageConfig entry
  (**no `computed_union_fmt`**, HIGH-3); `map_csharp_type()`; `apply_csharp_computed_wrapping()`;
  `is_already_list` csharp; **`map_types()` first-pass line AND idempotency-guard update (CRIT-2)**;
  `apply_disambiguated_type()` csharp branch; meta.py `_csharp_type`; **both `make_test_base` sites**
  gain `"_csharp_type": None` (LOW-1).
- 1.4 `main.py csharp` command. 1.5 `main.py all --csharp-folder`.
- 1.6 `tests/csharp_static/` xUnit v2 project. 1.7 `myairtable-tests/csharp/` skeleton (+ AssemblyInfo
  parallelization-off, PriorityOrderer, CrudFixture). 1.8 build.sh. 1.9 test.sh (cs case + loop).
  1.10 tests checks.sh. 1.11 myairtable checks.sh. 1.12 `dotnet tool install -g csharpier`.
- 1.13 **Prototype gate** `TestPocoModel.cs` proving: (a) parameterless-ctor + property decode incl.
  computed `[JsonInclude]` private-set; (b) **global-registration** generic factory round-trips —
  `MaybeSpecialOrError<string|double|DateTimeOffset>`, `VecOrValue<string>`,
  **`VecOrValue<DateTimeOffset>`**, nested `VecOrValue<MaybeSpecialOrError<string>>`, **null-valued
  computed decode** — decode AND encode, NO field attributes (§2.3.4, HIGH-5/R-new-2); (c) Duration =
  numeric seconds; (d) `[JsonIgnore]` snapshot + writable-only `JsonObject` payloads; (e)
  object-initializer creation.

**Exit**: `uv run main.py csharp <folder>` exits 0; both csproj build; prototype green; both
checks.sh/test.sh csharp sections run clean.

### Features 2–11

As v1 §5 (Static Runtime Core → Minimal Generator/first integration at F3.7 → ORM+Serialization →
Complex Types → Linked Records → Formula Builders → Formula Runtime Transpilation → Caching →
Serialization integration → Parity Audit & Polish), with:

- **F8.1** carrying the full transpiler C#-arm checklist from §3.1 (CRIT-1/4/5, HIGH-2/4, MED-1/2/6).
- **F3.2** the generated per-enum `JsonConverter<T>` (MED-4).
- **F4.3** `field_name_map` built with `name_pascal()` (MED-6); evaluate methods return `JsonNode?`.
- **F2.1** `AirtableException` = abstract base + **7** sealed subclasses incl. `NetworkError`
  (cross-language parity); `TestAirtableExceptionDecoding.cs` covers all 7.
- **F2.2** `VecOrValue`/`MaybeSpecialOrError` as `abstract record` + nested `sealed record` cases;
  value carriers (Attachment/Collaborator/Button/Record/Sort/SpecialNumber/ErrorValue) as `record`s.
- **F2.7** `CacheStore` guarded by `SemaphoreSlim` (async-aware), split-lock check-fetch-store.
- **F2.3 / F9** client retry covers **429 + 5xx** with jitter; `CancellationToken` threaded everywhere;
  transport failures → `NetworkError`.

## 6. Dependency Graph

```
F1 ──► F2 ──► F3 ──► F4 ──┬─► F5
                          ├─► F6
                          ├─► F7 ──► F8
                          ├─► F9
                          └─► F10
All ──────────────────────────► F11
```

## 7. Risks & Mitigations

| #   | Risk                                                                         | Mitigation                                                                                                      |
| --- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| R1  | STJ can't set computed (read-only) properties                                | §2.3.1 `[JsonInclude]`+private set; F1.13(a)                                                                    |
| R2  | Generic deser of nested `VecOrValue<MaybeSpecialOrError<T>>` via STJ factory | §2.3.4 `JsonConverterFactory` + global registration + through-`options` delegation; F1.13(b) nested+date+null   |
| R3  | STJ JSON-null = C# null (no NullNode); transpiler must emit bare null        | §2.3.3 + §3.1 arms 11/12/14; test_formula_transpiler_csharp.py                                                  |
| R4  | STJ default `TimeSpan` converter emits `"00:00:30"`                          | Custom numeric-seconds converter; F1.13(c)                                                                      |
| R5  | C# keyword collision                                                         | `_csharp_ident()` `@`-verbatim + unit tests                                                                     |
| R6  | URL encoding (`+`, spaces, path vs query)                                    | §2.3.9 verify-first spike; TestClientUrlEncoding; live round-trip                                               |
| R7  | `Math.Exp(1.0)` ULP mismatch                                                 | Verify-first; pin `EXP(1.0)==Math.E` if needed                                                                  |
| R8  | Transpiler emits Java-isms / wrong casing / missing `V()` boxing             | §3.1 explicit 18-point arm checklist (CRIT-1/4/5, HIGH-2/4, MED-1/2/6); transpiler unit tests                   |
| R9  | Disambiguated lookup/rollup skip C# types; stale types on cached `map_types` | F1.3 first-pass line + `apply_disambiguated_type()` + **idempotency-guard update (CRIT-2)** + unit test         |
| R10 | csharpier missing / fights generated style                                   | `command -v` guards both repos; never format generated output                                                   |
| R11 | xUnit new-instance-per-test + no built-in ordering (CRUD phasing)            | §2.4 `IClassFixture<CrudFixture>` + `[TestCaseOrderer]`/`PriorityOrderer`; xUnit v2; assembly-attr parallel-off |
| R12 | Native-AOT/source-gen incompat with reflection factory                       | Non-goal (§1); reflection serialization only                                                                    |
| R13 | `DateTimeOffset` vs `DateTime`                                               | §2.3.6 DateTimeOffset chosen; flagged for user review                                                           |
| R14 | `double` equality surprises                                                  | `Assert.Equal(42.0, x)`; Airtable-numbers-are-double documented                                                 |
| R15 | enum string-value (de)serialization parity (.NET 8 has no per-member names)  | Generated per-enum `JsonConverter<T>` keyed on raw strings (MED-4); TestSerializing covers                      |
| R16 | `dotnet test` cold-start / restore slowness                                  | `dotnet restore` once in build.sh; build-server reuse                                                           |
| R17 | `JsonNode` `==` reference-equality used for value comparison                 | `AirtableRuntime.IsEqual` via `JsonNode.DeepEquals` + N/S coercion (HIGH-2/MED-7); §2.3.3                       |
| R18 | Async cache: `lock` held across `await` → deadlock / pool starvation         | `SemaphoreSlim` + split-lock check-fetch-store (§2.3.8); Kotlin-`Mutex` analog, not Java's `lock`               |
| R19 | Error-variant parity gap (missing `NetworkError`)                            | 7-variant set matching Swift/Kotlin/Java (§2.3.7); TestAirtableExceptionDecoding covers all 7                   |
| R20 | STJ converter for record-based generic sum types                             | `JsonConverterFactory` works with records; F1.13(b) proves decode+encode for the record shapes                  |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py csharp <folder>` generates a compiling C# source set.
- [ ] `uv run main.py all --csharp-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with C# included.
- [ ] `./test.sh all` (myairtable-tests) green with C# included (nine languages).
- [ ] All **ten** integration scenario files green (struct/orm crud ×3, serializing, filter, runtime,
      caching, linked, complex, special-deser) — excludes Harness/Setup/Orderer/Fixture infra.
- [ ] Unit-test parity: 16 csharp_static files matching Java's inventory; formula builder + runtime
      counts within ±5% of Rust/Java.
- [ ] Upsert + dual ID/name Fields access + DX helpers (RequireId/Value/WithView) tested.
- [ ] Generated code is idiomatic C# 12 (auto-properties, object initializers, async/await, exception
      hierarchy, `@`-verbatim escapes, no Java-isms).
