# C# Language Support — Implementation Plan v1

## 1. Overview & Goals

Add full-parity **C#** code generation to `myairtable` — the ninth target, alongside
Python, TypeScript, JavaScript, Rust, Swift, Kotlin, Java, and Go. The closest template is
the **Java** target (completed 2026-06-12, epic `myairtable-kree`): same one-public-type-per-file
discipline, same boxed-JSON-node runtime value, same sum-type wrapper strategy, same
test-base semantics. But the generated code must feel **idiomatic modern C# (.NET 8 / C# 12)** —
not Java-with-properties: async/await `Task` methods, auto-properties with object-initializer
construction, `System.Text.Json` with custom converters, `DateTimeOffset`/`TimeSpan`, a single
file-scoped `namespace`, exception hierarchy (all unchecked in C#), `@`-verbatim keyword escaping.

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
trim-safe — explicit non-goal, §2.3.4); `netstandard2.0` multi-targeting; synchronous API
variants; F#/VB consumption concerns; `.sln` emission (generator writes source only).

## 2. Design Decisions

### 2.1 User-approved (2026-06-16)

| #   | Question       | Answer                                                    |
| --- | -------------- | --------------------------------------------------------- |
| 1   | Async model    | **async/await `Task`/`Task<T>`** + `CancellationToken`    |
| 2   | Target FW      | **.NET 8 (LTS)** — `net8.0`, C# 12, nullable refs enabled |
| 3   | JSON library   | **System.Text.Json** (custom `JsonConverter`s for sums)   |
| 4   | Test framework | **xUnit** (unit + integration)                            |

Build tooling: **.NET SDK / MSBuild**, hand-written `.csproj` in consuming projects (generator
emits no project/build files — parity with all other targets). HTTP via shared `HttpClient`.

### 2.2 Java-pattern → C# idiom mapping

| Java construct                                                     | C# equivalent                                                                                                                                 |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `final class AirtableClient` + JDK HttpClient + `ReentrantLock`    | `sealed class AirtableClient` + `HttpClient` (shared) + `lock`/`SemaphoreSlim`; **async** methods                                             |
| Mutable POJO + no-arg ctor + Jackson field-access                  | Mutable class + **public parameterless ctor** + auto-properties; STJ property-based decode (§2.3.1)                                           |
| Jackson `JsonNode` (type-erased value)                             | `System.Text.Json.Nodes.JsonNode` (mutable DOM). **JSON null = C# `null` JsonNode, no `NullNode` sentinel** (§2.3.3)                          |
| `sealed interface VecOrValue<T>` + ContextualDeserializer          | `abstract class VecOrValue<T>` (`Single`/`Multiple`) + **generic `JsonConverterFactory`**, registered **globally** in shared options (§2.3.4) |
| `sealed interface MaybeSpecialOrError<T>`                          | `abstract class MaybeSpecialOrError<T>` (`Value`/`Special`/`Error`) + factory converter                                                       |
| `enum` + `@JsonValue`/`@JsonCreator`                               | `enum` + `[JsonConverter]` (string-value converter) **or** `[EnumMember]`-style custom converter (§2.4)                                       |
| `sealed abstract class AirtableException extends RuntimeException` | `abstract class AirtableException : Exception` + sealed subclasses; C# exceptions all unchecked (§2.3.7)                                      |
| Plain blocking method                                              | `async Task<T> …Async(…, CancellationToken)`                                                                                                  |
| `final class AirtableRuntime` static methods                       | `static class AirtableRuntime` — owns ALL coercions V/N/S/A/AN/AS/D/IsTruthy + ~80 functions (§2.3.3)                                         |
| `public static final f` filter accessor                            | `public static readonly PrimaryFilters F` → `PrimaryModel.F.PrimaryKey.Eq(...)`                                                               |
| `_java_ident()` `_`-suffix rename (no escape in Java)              | **`@`-verbatim identifier** (`@class`, `@event`) — C# HAS an escape mechanism (§2.3.5)                                                        |
| `java.time.Instant` + custom serializer                            | `DateTimeOffset` + custom converter (3-format decode)                                                                                         |
| `java.time.Duration`, wire = numeric seconds                       | `TimeSpan` + custom converter, wire = **numeric seconds** (§2.3.6)                                                                            |
| Generated nested `Builder` (writable fields)                       | **Object-initializer** `new PrimaryModel { PrimaryKey = "x" }` — no builder, no Create class (§2.3.11)                                        |
| Per-model fluent `save()/fetch()/delete()` (no reified generics)   | Per-model `SaveAsync()/FetchAsync()/DeleteAsync()` covariant returns → `ModelOps` (C# generics ARE reified — §2.3.12)                         |
| `RecordId` in Javadoc only                                         | `string` (no alias); `RecordId` appears in XML doc comments only                                                                              |

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
- **Writable** fields: `{ get; set; }` (settable via object initializer = the creation idiom, §2.3.11).
- **Computed** fields: `[JsonInclude] public T? Name { get; private set; }` — STJ sets the private
  setter during deserialization (STJ honors `[JsonInclude]` on non-public setters); user cannot
  mutate, and object-initializer creation omits them. This is the read-only contract.
- `[JsonPropertyName(...)]` raw values are **field IDs**.
- Create/update payloads are **hand-rolled** (`ToCreateFields()` / `DirtyFields()` returning
  `JsonObject` / `Dictionary<string, JsonNode?>` over writable field IDs only). The shared options
  are used wholesale only for **decoding**.
- Dirty tracking: `[JsonIgnore] private Dictionary<string, JsonNode?> _snapshot` + diff (port of
  Java/Kotlin/Swift/Rust).
- Numbers are nullable value types (`double?`, `long?`, `bool?`) so absent ≠ default-zero.

#### 2.3.2 Filter DSL uses `Eq` / `Neq`

C# has the same footgun as Java/Kotlin: `Equals(object)` exists on every type, so a generated
`Equals(string)` overload would shadow/confuse against `object.Equals`. Keep **`Eq`/`Neq`** (PascalCase);
all other names match the other languages (`Contains`, `StartsWith`, `GreaterThan`, `IsEmpty`/
`IsNotEmpty`, …). Accessor: `public static readonly PrimaryFilters F = new();` →
`PrimaryModel.F.PrimaryKey.Eq("x")`.

#### 2.3.3 `JsonNode` is the type-erased value; ALL coercions on `AirtableRuntime`; JSON-null = C# null

The formula runtime operates on `System.Text.Json.Nodes.JsonNode?`. Every coercion helper —
`V`, `N`, `S`, `A`, `AN`, `AS`, `D`, `IsTruthy` — is a **static method on `AirtableRuntime`**, so
the transpiler's single `_runtime = "AirtableRuntime"` qualifier covers all of them (Java model).

**Critical C# divergence from Java**: System.Text.Json represents a JSON `null` as a C# `null`
`JsonNode` reference — there is **no `NullNode` sentinel** (unlike Jackson). So:

- `V(null)` returns `null` (not a node); the runtime/`IsTruthy` treats `null` JsonNode as **BLANK**.
- The transpiler emits the bare `null` literal where Java emits `NullNode.getInstance()`.
- Number/string/bool literals use `JsonValue.Create(value)` (returns `JsonValue` : `JsonNode`).

```csharp
public static JsonNode? V(object? value) =>
    value is null ? null : JsonSerializer.SerializeToNode(value, AirtableJson.Options);
```

`SerializeToNode` with the shared options (Instant/Duration converters registered) handles every
field type inside `V()`.

#### 2.3.4 Generic sum-type converters: `JsonConverterFactory`, registered globally (CRIT)

System.Text.Json's analog of Java's `ContextualDeserializer` is a **`JsonConverterFactory`**:

- `VecOrValueConverterFactory.CanConvert(t)` → `t.IsGenericType && t.GetGenericTypeDefinition() == typeof(VecOrValue<>)`.
- `CreateConverter(t, options)` reflects the element type and instantiates
  `VecOrValueConverter<T>` via `Activator.CreateInstance(typeof(VecOrValueConverter<>).MakeGenericType(elem))`.
- `VecOrValueConverter<T>.Read` peeks the token (`reader.TokenType == JsonTokenType.StartArray`
  → `Multiple(List<T>)`, else `Single(T)`), delegating element (de)serialization to
  `options.GetConverter(typeof(T))` — so **nested `VecOrValue<MaybeSpecialOrError<T>>` resolves
  automatically** when both factories are registered in the shared `JsonSerializerOptions`.
- `MaybeSpecialOrError<T>`: object with `"specialValue"` → `Special`; object with `"error"` →
  `Error`; else deserialize to `T` → `Value`.

**Registration is GLOBAL** (both factories added once to `AirtableJson.Options`), which is _cleaner
than Java's field-level annotations_ — STJ resolves generics through the options chain. The generator
therefore does **not** emit per-field converter attributes (a meaningful simplification vs Java/Kotlin).

**F1.13 prototype gate** must prove: global-registration round-trips for `MaybeSpecialOrError<string>`,
`<double>`, `<DateTimeOffset>`, `VecOrValue<string>`, and the nested
`VecOrValue<MaybeSpecialOrError<string>>` — **decode AND encode** — using only options-level
registration (no field attributes). This is the single riskiest C# foundation.

#### 2.3.5 Single namespace `MyAirtable`; one public type per file; `@`-verbatim keyword escape

All files (static + generated) declare a file-scoped `namespace MyAirtable;`. **C# decouples
namespace from directory** (unlike Go/Java packages), so the Models/Options/Types/Formulas/Tables
folder split is purely organizational — **no package-vs-directory compile gate is needed** (a
genuine simplification over the Java/Go plans). One public type per file by convention; tightly
coupled helpers nest (`Single`/`Multiple` inside `VecOrValue`; `Thumbnail` inside `AirtableThumbnails`;
exception subclasses nested in `AirtableException`).

**Keyword escaping**: C# supports **verbatim identifiers** (`@class`, `@namespace`, `@event`), so
`_csharp_ident()` prefixes reserved words with `@` (keeping the logical name) rather than renaming
(Java's `_`-suffix). The escape is invisible in JSON (field IDs come from `[JsonPropertyName]`) and
in the public surface the `@` is only on the rare collision. Reserved set = C# reserved keywords;
contextual keywords (`value`, `async`, `await`, `record`, …) only need `@` in specific positions and
are escaped defensively.

#### 2.3.6 Date / Duration / numbers

- `DateTimeOffset` for datetimes (idiomatic absolute timestamp ≈ Java `Instant`). Custom converter
  decode order: ISO-8601-with-offset → ISO-8601 (assume UTC) → date-only `YYYY-MM-DD`
  (→ midnight UTC). Encode ISO-8601. (Open for review: `DateTime` (Utc kind) is the alternative;
  `DateTimeOffset` chosen for offset fidelity.)
- Duration → `TimeSpan`, wire = **numeric seconds** (locked by Swift/Kotlin live verification).
  **Risk**: STJ's built-in `TimeSpan` converter emits the string form `"00:00:30"` — the custom
  converter MUST read/write numeric seconds (`TimeSpan.FromSeconds` / `.TotalSeconds`). F1.13 asserts.
- Airtable `number` fields are ALWAYS `double` (never `long`) — tests use `42.0`. `autoNumber`/`count`
  map to `long` (matches `GENERIC_TO_JAVA`/`GENERIC_TO_KOTLIN`).
- **`Math.Exp(1.0)` ULP check**: verify .NET's value against V8/Airtable `Math.E`; if it differs by
  a ULP (as JVM does), port the pinned `EXP(1.0) == Math.E` special case. Verify-first in the runtime task.

#### 2.3.7 Errors: unchecked exception hierarchy

`public abstract class AirtableException : Exception` with sealed subclasses
`HttpError(status, body)`, `ApiError(code, message)`, `DecodingError(inner)`, `InvalidUrlError`,
`MissingCredentialsError`, `RateLimitedError(retryAfterSeconds)`. All C# exceptions are unchecked
(no `throws` poisoning). Pattern-matching `switch` over the hierarchy works in tests. (Naming uses
the `Error` suffix that .NET analyzers expect for exception types; subclasses are `…Error` not bare nouns.)

#### 2.3.8 Concurrency

`sealed class AirtableClient`, async methods returning `Task`/`Task<T>` with `CancellationToken`.
A single shared static `HttpClient` (thread-safe, avoids socket exhaustion). `CacheStore` guards its
maps with `lock` for synchronous dictionary ops; cache-miss population does the async HTTP fetch
**outside** the lock, then stores under the lock (check-fetch-store). 429 retry/backoff uses
`await Task.Delay(retryAfter, ct)`.

#### 2.3.9 URL encoding verify-first

.NET `Uri.EscapeDataString("+")` → `%2B` (likely correct — opposite of the Ktor/Swift raw-`+` bug).
But **verify-first spike**: confirm a `filterByFormula` of `LEN({field})+1` round-trips against the
real base (build query strings with `Uri.EscapeDataString` per value, never a helper that turns
space→`+`). Path segments (table names) also use `Uri.EscapeDataString`. Pinned by `TestClientUrlEncoding.cs`.

#### 2.3.10 Formatter & lint

**CSharpier** (opinionated reflow formatter, the C# analog to google-java-format/ktlint;
`dotnet tool install -g csharpier`) with `command -v csharpier` warn-skip guards in BOTH repos'
checks.sh. Scope: `static/csharp/`, `tests/csharp_static/`, `myairtable-tests/csharp/` — **NEVER
generated output**. The generator emits CSharpier-style output so runtime files stay stable. A shared
`.editorconfig` pins brace/indent style. (`dotnet format` is the SDK-built-in fallback but only does
editorconfig whitespace, not reflow — CSharpier matches the other languages' opinionated formatters.)

#### 2.3.11 Creation idiom: object initializer (no builder)

C#'s **object-initializer** syntax is the creation idiom — `new PrimaryModel { PrimaryKey = "x" }` —
strictly nicer than Java's builder and requiring zero generated ceremony (writable props are already
`{ get; set; }`). No builder, no separate `Create{Table}` type (cross-language decision stands).
Plain property setters cover post-fetch mutation (`model.Email = …;` before `SaveAsync()`).

#### 2.3.12 Model DX surface: `AirtableModel` base + per-model fluent async methods

`AirtableModel` is an **abstract base class** (cleaner than Java's interface — it can hold the shared
`Id`, `CreatedTime`, `AttachedClient`, `_snapshot` state):

- Members: `Id`, `CreatedTime`, `AttachedClient`, `TakeSnapshot()`, `DirtyFields()`, `ToRecord()`,
  `ToCreateFields()`, `IsNew`; `RequireId()` / `RequireAttachedClient()` (throw `ApiError`/missing-client).
- C# generics **are reified**, so fluent CRUD could use a generic `ModelOps` without class tokens.
  To match Java exactly and keep covariant returns, the generator emits per-model
  `public Task<PrimaryModel> SaveAsync(CancellationToken ct = default) => ModelOps.SaveAsync(this, ct);`
  (likewise `FetchAsync`/`DeleteAsync`). `ModelOps` is a static async helper using `GetType()` /
  generic `<T>` for decode (no `Class<T>` token needed — a C# simplification).
- DX value accessors (Kotlin `.value`/`.cleanValues`): `T? Value` property on `MaybeSpecialOrError<T>`
  (null unless `Value`); `Values()`/`CleanValues()` on `VecOrValue<T>` /
  `VecOrValue<MaybeSpecialOrError<T>>`. Covered by `TestDxHelpers.cs`.

### 2.4 Other settled choices

| Decision            | Value                                                                                                                                                                                                                                                                             |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Test framework      | **xUnit** (`Xunit`, `Assert.*`)                                                                                                                                                                                                                                                   |
| Integration phasing | xUnit creates a new class instance per test → shared CRUD state via **`IClassFixture<T>`** (holds created IDs); ordering via a custom **`PriorityOrderer` + `[TestPriority(n)]`** attribute (test-support helper) — the analog to Java's `PER_CLASS` + `@TestMethodOrder` (§ R11) |
| Test parallelism    | Cross-class parallelism OFF (`[assembly: CollectionBehavior(DisableTestParallelization = true)]`); distinct primary keys per file (`"CSharp StructCrud PKOnly {ts}"`)                                                                                                             |
| File naming         | `PascalCase.cs` (one public type = filename); properties `PascalCase` (C# convention — NOT camelCase) via a `name_pascal()` helper                                                                                                                                                |
| Select-option enums | C# enum; member names PascalCase via `_choice_to_entry()` port; raw string value via custom `JsonStringEnum`-style converter or `[JsonPropertyName]`-keyed converter; dedup collisions (v2/v3 suffix parity)                                                                      |
| Linked records      | Raw `List<string>` record IDs; resolve via `airtable.Secondary.GetAsync(ids)`                                                                                                                                                                                                     |
| Dirty tracking      | `[JsonIgnore]` snapshot dict + diff (port of Java/Kotlin/Swift/Rust)                                                                                                                                                                                                              |
| Table accessors     | `airtable.Primary` **properties** (C# idiom — not `primary()` methods)                                                                                                                                                                                                            |
| `.csproj`           | NOT emitted by generator — hand-written in consuming projects                                                                                                                                                                                                                     |
| XML doc comments    | `/// <summary>…</summary>`, `<c>fieldId</c>`, formula text in `<code>…</code>` (escape `<`/`>`/`&` — unit-tested)                                                                                                                                                                 |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/csharp.py              # NEW ~1000-1100 LOC (mirrors java.py structure)
src/utils/write_to_csharp_file.py     # NEW WriteToCSharpFile (XML doc, region, class/enum/property/
                                      #   method helpers, _csharp_ident() @-verbatim escape,
                                      #   _choice_to_entry(), _csharp_string_literal(), name_pascal())
src/utils/type_mapper.py              # MOD: GENERIC_TO_CSHARP; "csharp" in Language literal (:361);
                                      #   LanguageConfig entry (list_fmt="List<{0}>",
                                      #   union_fmt="VecOrValue<{0}>",
                                      #   computed_union_fmt="VecOrValue<MaybeSpecialOrError<{0}>>",
                                      #   unknown="JsonNode"); map_csharp_type();
                                      #   apply_csharp_computed_wrapping(); is_already_list csharp case
                                      #   (List<); map_types() first-pass csharp line (~:234-239);
                                      #   apply_disambiguated_type() csharp branch (~:949-959)
src/utils/write_to_file.py            # MOD: "csharp" in language Literal (:49) + header match case
                                      #   (:74 — // comments, same branch as java/go)
src/meta.py                           # MOD: _csharp_type PrivateAttr + csharp_type property
src/formulas/formula_transpiler.py    # MOD (enumerated): "csharp" in Language literal (:21);
                                      #   _self — csharp → "this" (:323-328 group); _runtime — ADD
                                      #   csharp to the AirtableRuntime branch (:333); csharp arms in
                                      #   ALL ~28 guarded blocks: literals (bare `null` NOT NullNode,
                                      #   JsonValue.Create(...) for num/str/bool — §2.3.3),
                                      #   FieldRef → AirtableRuntime.V(this.X) (QUALIFIED, PascalCase
                                      #   prop), AND/OR/NOT/XOR via AirtableRuntime.IsTruthy + &&/||/!,
                                      #   IF via ternary, IFS/SWITCH, LEN/BLANK/TRUE/FALSE/RECORD_ID,
                                      #   _emit_str/_emit_num → QUALIFIED AirtableRuntime.S()/N()
                                      #   (like Java, not bare), _emit_binary_op/_emit_unary_op,
                                      #   runtime-call fallthrough; _csharp_ident escaping
main.py                               # MOD: `csharp` command + `all --csharp-folder`
checks.sh                             # MOD: csharp section (csharpier guard + `dotnet test` in
                                      #   tests/csharp_static; warn-skip if no dotnet)
static/csharp/                        # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestCSharp* classes; make_test_base
                                      #   __pydantic_private__ gains "_csharp_type": None
tests/test_formula_transpiler_csharp.py  # NEW (mirror Java twin, ~45-50 cases)
tests/csharp_static/                  # NEW xUnit project
  ├── CSharpStatic.Tests.csproj       #   net8.0; xUnit; <Compile Include="../../static/csharp/**/*.cs"/>
  └── *.cs                            # 16 files = Java parity
      ├── TestPocoModel.cs            # F1.13 prototype gate (§2.3.1/2.3.4/2.3.5/2.3.6)
      ├── TestHarness.cs
      ├── TestAirtableQueryBuild.cs
      ├── TestAirtableExceptionDecoding.cs
      ├── TestCacheStore.cs
      ├── TestClientCachePolicy.cs
      ├── TestClientHardening.cs
      ├── TestClientUrlEncoding.cs
      ├── TestDateDecoding.cs
      ├── TestDxHelpers.cs            # RequireId, Value/CleanValues, WithView
      ├── TestSpecialErrorDecoding.cs
      ├── TestFieldsDualAccess.cs
      ├── TestValueCoercion.cs
      ├── TestTableBoundedOps.cs
      ├── TestFormula.cs              # ~86 builder cases
      └── TestAirtableRuntime.cs      # ~180 runtime cases
```

### 3.2 Generated output (per run)

```
csharp/output/                    # generator does NOT emit .csproj/.sln
├── dynamic/
│   ├── Models/{Table}Model.cs
│   ├── Options/{Table}Options.cs
│   ├── Types/{Table}Fields.cs
│   ├── Formulas/{Table}Filters.cs
│   └── Tables/{Table}Table.cs
├── static/                       # copied from static/csharp/
└── Airtable.cs
```

All files declare `namespace MyAirtable;` (no compile gate — §2.3.5).

### 3.3 Test repo (`myairtable-tests`)

```
csharp/
├── CSharpTests.csproj            # HAND-WRITTEN: net8.0; xUnit; HttpClient/STJ;
│                                 #   <Compile Include="output/**/*.cs"/>
├── xunit.runner.json             # disable test parallelization
├── output/                       # regenerated by build.sh
└── tests/
    ├── TestHarness.cs            # smoke: MyAirtableRuntimeInfo.Version reachable
    ├── TestSetup.cs              # .env walker + Airtable factory + PrimaryKey(suite, label)
    ├── PriorityOrderer.cs        # xUnit ITestCaseOrderer + [TestPriority] (§ R11)
    ├── TestStructCrudViaTable.cs
    ├── TestOrmCrudViaTable.cs
    ├── TestOrmCrudViaModel.cs
    ├── TestSerializing.cs
    ├── TestFilterByFormula.cs
    ├── TestRuntimeFormulas.cs
    ├── TestCaching.cs
    ├── TestLinkedRecords.cs
    ├── TestComplexProperties.cs
    └── TestSpecialErrorDeser.cs
build.sh                          # MOD: --csharp-folder ./csharp/output
test.sh                           # MOD: cs case + ADD cs to `for lang in ts js py rs swift kotlin java go`
checks.sh                         # MOD: csharpier (command -v guard) + `dotnet build csharp`
```

`test.sh` cs case (xUnit filters by FQN/display-name via `dotnet test --filter`):

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

One public type per file. Nested types noted inline.

| File                                            | Contents                                                                                                                                                                         |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AirtableException.cs`                          | abstract base + sealed subclasses HttpError, ApiError, DecodingError, InvalidUrlError, MissingCredentialsError, RateLimitedError(retryAfterSeconds) (§2.3.7)                     |
| `AirtableClient.cs`                             | shared `HttpClient`, bearer auth, **async** record endpoints, 429 retry/backoff (`Task.Delay`), owns CacheStore, chunk-of-10 batching; query/path encoding (§2.3.9)              |
| `AirtableJson.cs`                               | Shared `JsonSerializerOptions` singleton (PropertyNameCaseInsensitive, DefaultIgnoreCondition=WhenWritingNull, both sum-type factories + Instant/Duration converters registered) |
| `AirtableDateConverter.cs`                      | `DateTimeOffset` 3-format decode converter                                                                                                                                       |
| `AirtableDurationConverter.cs`                  | `TimeSpan` ↔ numeric seconds (§2.3.6)                                                                                                                                            |
| `CacheStore.cs`                                 | TTL + LRU behind `lock`; per-table wipe; `InvalidateAll()`                                                                                                                       |
| `AirtableModel.cs`                              | abstract base (§2.3.12): Id/CreatedTime/AttachedClient, TakeSnapshot(), DirtyFields(), ToRecord(), ToCreateFields(), IsNew, RequireId()/RequireAttachedClient()                  |
| `ModelOps.cs`                                   | static async SaveAsync/FetchAsync/DeleteAsync backing generated per-model fluent methods (§2.3.12)                                                                               |
| `AirtableQuery.cs`                              | formula, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldId; ToParameters(); WithView(IAirtableView)                                                                |
| `IAirtableView.cs`                              | `interface IAirtableView { string Id { get; } }` — implemented by generated `{Table}View` enums' converter/wrapper                                                               |
| `Fields.cs`                                     | Wraps `Dictionary<string, JsonNode?>`; dual ID/name Get/Set (ID-first, name fallback)                                                                                            |
| `DictTable.cs`                                  | Raw async CRUD returning Fields; mirrors OrmTable API                                                                                                                            |
| `OrmTable.cs`                                   | `OrmTable<T> where T : AirtableModel, new()` — typed async CRUD + UpsertAsync(model, matchFields), batching, cache invalidation                                                  |
| `Formulas.cs` + field classes                   | `Formulas` combinators (And/Or/Not/Xor) + Text/Number/Date/Boolean/Select/MultiSelect/Link/Id/Attachment field classes using Eq/Neq — one type per file                          |
| `AirtableRuntime.cs`                            | static class — ALL coercions V/N/S/A/AN/AS/D/IsTruthy (§2.3.3) + ~80 functions (math incl. EXP pin, logic, string, date via DateTimeOffset, array, regex)                        |
| `VecOrValue.cs`                                 | abstract class<T> + nested Single/Multiple + value accessors (Values/CleanValues)                                                                                                |
| `VecOrValueConverter.cs`                        | `JsonConverterFactory` + `VecOrValueConverter<T>` (§2.3.4)                                                                                                                       |
| `MaybeSpecialOrError.cs`                        | abstract class<T> + nested Value/Special/Error + `T? Value` accessor                                                                                                             |
| `MaybeSpecialOrErrorConverter.cs`               | `JsonConverterFactory` + `MaybeSpecialOrErrorConverter<T>`                                                                                                                       |
| `SpecialNumber.cs` / `ErrorValue.cs`            | records (`{"specialValue": …}` / `{"error": …}`)                                                                                                                                 |
| `AirtableRecord.cs`                             | generic record envelope (Id, CreatedTime, Fields)                                                                                                                                |
| `AirtableAttachment.cs`                         | + nested Thumbnails/Thumbnail                                                                                                                                                    |
| `AirtableCollaborator.cs` / `AirtableButton.cs` | data carriers                                                                                                                                                                    |
| `Sort.cs` / `SortDirection.cs`                  | sort spec + enum                                                                                                                                                                 |
| `MyAirtableRuntimeInfo.cs`                      | Version constant                                                                                                                                                                 |

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"csharp"` in `WriteToFile.language` literal (write_to_file.py:49) + header match case.
- 1.2 `write_to_csharp_file.py` (`WriteToCSharpFile` + reserved-word set + `_csharp_ident()`
  `@`-verbatim escape + `_choice_to_entry()` + `_csharp_string_literal()` + `name_pascal()` +
  XML-doc escaping).
- 1.3 Type system wiring — ALL of: `GENERIC_TO_CSHARP`; `"csharp"` in type_mapper `Language`
  literal; `LanguageConfig` entry; `map_csharp_type()`; `apply_csharp_computed_wrapping()`;
  `is_already_list` csharp case; **`map_types()` first-pass csharp line**;
  **`apply_disambiguated_type()` csharp branch** (both apply computed wrapping); meta.py
  `_csharp_type` PrivateAttr + property; `make_test_base` `__pydantic_private__` gains
  `"_csharp_type": None`.
- 1.4 `main.py csharp` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--csharp-folder`).
- 1.6 `tests/csharp_static/` xUnit project (net8.0; xUnit pins; `<Compile Include="../../static/csharp/**/*.cs"/>`).
- 1.7 `myairtable-tests/csharp/` skeleton (hand-written .csproj including `output/**/*.cs`; xunit.runner.json).
- 1.8 `myairtable-tests/build.sh`: `--csharp-folder`.
- 1.9 `myairtable-tests/test.sh`: cs case (§3.3) AND add `cs` to the `all` loop.
- 1.10 `myairtable-tests/checks.sh`: csharpier `command -v` guard + `dotnet build csharp`.
- 1.11 `myairtable/checks.sh`: csharp section (csharpier guard + `dotnet test` in
  tests/csharp_static; warn-skip if no dotnet).
- 1.12 `dotnet tool install -g csharpier` (document in setup).
- 1.13 **Prototype gate** `TestPocoModel.cs` proving ALL risky foundations before any
  templating: (a) parameterless-ctor + property decode of `[JsonPropertyName]` field-ID keys
  incl. computed (`[JsonInclude]` private-set) fields; (b) **global-registration** generic
  `JsonConverterFactory` round-trips — `MaybeSpecialOrError<string>`, `<double>`,
  `<DateTimeOffset>`, `VecOrValue<string>`, nested `VecOrValue<MaybeSpecialOrError<string>>` —
  decode AND encode, NO field attributes (§2.3.4); (c) Duration encodes as numeric seconds
  (not `"00:00:30"`); (d) `[JsonIgnore]` snapshot + writable-only `JsonObject` payload builders;
  (e) object-initializer creation for writable-only fields.

**Exit**: `uv run main.py csharp <folder>` exits 0 (stub ok); both csproj projects build;
prototype green; both checks.sh and test.sh run their csharp sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `AirtableException.cs` hierarchy.
- 2.2 Types: `VecOrValue` (+Converter factory), `MaybeSpecialOrError` (+Converter factory),
  `SpecialNumber`, `ErrorValue`, `AirtableRecord`, `AirtableAttachment`, `AirtableCollaborator`,
  `AirtableButton`, `Sort`/`SortDirection`, `IAirtableView`, `AirtableDateConverter`,
  `AirtableDurationConverter`.
- 2.3 `AirtableClient.cs` — **starts with the URL-encoding verification spike** (§2.3.9).
- 2.4 `AirtableQuery.cs` incl. `WithView`; 2.5 `Fields.cs`; 2.6 `DictTable.cs`;
  2.7 `CacheStore.cs` skeleton (API + lock; TTL/LRU population deferred to F9).
- 2.8 `AirtableJson.cs` (options singleton w/ both factories) + `AirtableRuntime` coercion statics (§2.3.3).
- 2.9 Unit tests: TestAirtableQueryBuild, TestAirtableExceptionDecoding, TestFieldsDualAccess,
  TestDateDecoding, TestSpecialErrorDecoding, TestValueCoercion, TestClientUrlEncoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration test ASAP

- 3.1 `generate_csharp()` entry + static copy (exclude AirtableRuntime.cs / Formula files per flags).
- 3.2 `write_options()` — enum per select field; PascalCase members; string-value converter; dedup (v2/v3).
- 3.3 `write_field_types()` — `{Table}Fields` class (per-field Id/Name constants, IdByName/NameById
  maps, AllIds) + `{Table}View` enum.
- 3.4 `write_tables()` (dict accessor only).
- 3.5 `write_main()` — `sealed class Airtable(baseId, apiKey, cacheSeconds)` with per-table
  accessor **properties**.
- 3.6 Offline unit tests (content assertions; no compile shell-out).
- 3.7 **Integration**: `TestStructCrudViaTable.cs` green against the real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `AirtableModel.cs` base (§2.3.12) + `ModelOps.cs`; 4.2 `OrmTable.cs` incl. UpsertAsync.
- 4.3 `write_models()` — parameterless ctor + auto-properties per §2.3.1; `[JsonPropertyName]`
  field IDs; `[JsonInclude]` private-set computed; snapshot dirty tracking; per-model
  `SaveAsync()/FetchAsync()/DeleteAsync()`; XML doc per field; evaluate methods when runtime=True.
- 4.4 `write_tables()` ORM accessor.
- 4.5 Unit tests `TestCSharpComputedFields`: computed = private set + not object-initializable
  conceptually; writable = public set; `[JsonPropertyName]` IDs present; payload builders exclude
  computed; evaluate methods gated on runtime flag.
- 4.6 Offline `TestSerializing.cs` (8 parity cases from the Java/Kotlin/Swift list).
- 4.7 **Integration**: TestOrmCrudViaTable (primary-key-only, all-simple-props, upsert-as-create/update,
  111-record batch, field selection, maxRecords, invalid-ID error), TestOrmCrudViaModel (Save/Fetch/Delete).

### Feature 5 — Complex Field Types [P2]

- 5.1 Attachment upload (URL-based, TS parity); 5.2 collaborator encode/decode; 5.3 computed
  `MaybeSpecialOrError` end-to-end decode; 5.4 button decode; 5.5 duration round-trip magnitude.
- 5.6 **Integration**: TestComplexProperties.cs + complex sections of CRUD files.
- 5.7 **Integration**: TestSpecialErrorDeser.cs (parity w/ Rust/Swift/Kotlin/Java).

### Feature 6 — Linked Records [P2]

- 6.1 Generator: raw `List<string>` record-ID fields (no wrapper).
- 6.2 **Integration**: TestLinkedRecords.cs — link arrays + resolution via `airtable.Secondary.GetAsync(ids)`.

### Feature 7 — Formula Builders [P2]

- 7.1 Field classes (Eq/Neq per §2.3.2); 7.2 combinators; 7.3 `write_formula_helpers()` →
  `{Table}Filters` + `public static readonly F` on models.
- 7.4 Unit tests `TestFormula.cs` (~86 cases mirroring Rust/Kotlin/Java categories).
- 7.5 **Integration**: TestFilterByFormula.cs.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler wiring exactly as enumerated in §3.1: Language literal (:21), `_runtime` initializer
  (:333), csharp arms in ALL ~28 guarded blocks with `JsonValue.Create`/bare-`null` literals,
  **qualified** `AirtableRuntime.V/S/N`, `_csharp_ident` escaping. Evaluate methods return `JsonNode?`.
- 8.2–8.8 `AirtableRuntime.cs` groups: math (incl. EXP pin §2.3.6), logic, string, date (DateTimeOffset),
  array, regex.
- 8.9 Generator wires evaluate methods on models (return `JsonNode?`).
- 8.10 `tests/test_formula_transpiler_csharp.py` (mirror Java twin).
- 8.11 `TestAirtableRuntime.cs` ~180 cases (parity w/ Rust/Swift/Kotlin/Java).
- 8.12 **Integration**: TestRuntimeFormulas.cs.

### Feature 9 — Caching [P3]

- 9.1 CacheStore TTL/LRU/per-table wipe; 9.2 client cached read paths; 9.3 mutation invalidation;
  9.4 InvalidateAllCaches() + per-table invalidate.
- 9.5 **Integration**: TestCaching.cs (~10 scenarios, Rust/Java parity).

### Feature 10 — Serialization (integration portion) [P3]

- 10.1 Network-bound TestSerializing cases: linked-record ID arrays, createdTime round-trip,
  unsaved-id behavior.

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 File-by-file test diff vs Java/Kotlin/Swift/Rust/Python/TS; follow-ups for gaps (incl.
  TestDxHelpers, TestClientCachePolicy, TestClientHardening, TestTableBoundedOps).
- 11.2 `./checks.sh` both repos green; 11.3 `./test.sh all` green (nine languages);
  11.4 `main.py all` with csharp alongside others; 11.5 README updates (both repos).

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

| #   | Risk                                                                           | Mitigation                                                                                          |
| --- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| R1  | STJ can't set computed (read-only) properties                                  | §2.3.1 `[JsonInclude]` + private set; F1.13(a) gate                                                 |
| R2  | Generic deser of `VecOrValue<MaybeSpecialOrError<T>>` via STJ factory          | §2.3.4 `JsonConverterFactory` + global registration + nested resolution; F1.13(b) decode AND encode |
| R3  | STJ JSON-null = C# null JsonNode (no NullNode); transpiler must emit bare null | §2.3.3 explicit; transpiler csharp arms differ from Java; test_formula_transpiler_csharp.py         |
| R4  | STJ default `TimeSpan` converter emits `"00:00:30"` string                     | Custom numeric-seconds converter; F1.13(c) assert                                                   |
| R5  | C# keyword collision                                                           | `_csharp_ident()` `@`-verbatim escape + unit tests                                                  |
| R6  | URL encoding (`+`, spaces, path vs query)                                      | §2.3.9 verify-first spike; TestClientUrlEncoding; live formula round-trip                           |
| R7  | `Math.Exp(1.0)` ULP mismatch vs Airtable                                       | Verify-first; pin `EXP(1.0)==Math.E` if needed; runtime parity tests                                |
| R8  | Transpiler emits Java-isms for C# (NullNode, node ctors)                       | §3.1 explicit enumeration (JsonValue.Create / bare null); test_formula_transpiler_csharp.py         |
| R9  | Disambiguated lookup/rollup fields skip C# types                               | F1.3 explicit `map_types()` + `apply_disambiguated_type()` tasks + unit test                        |
| R10 | csharpier missing / fights generated style                                     | `command -v` guards both repos; never format generated output                                       |
| R11 | xUnit lacks built-in test ordering + new-instance-per-test (CRUD phasing)      | §2.4 `IClassFixture` shared state + custom `PriorityOrderer`/`[TestPriority]`; parallelization off  |
| R12 | Native-AOT/source-gen incompat with reflection generic factory                 | Non-goal (§1); reflection-based serialization only; documented                                      |
| R13 | `DateTimeOffset` vs `DateTime` choice                                          | §2.3.6 DateTimeOffset chosen (offset fidelity); flagged for user review                             |
| R14 | `double` equality surprises in tests                                           | `Assert.Equal(42.0, x)` with doubles; Airtable-numbers-are-double documented                        |
| R15 | `dotnet test` cold-start / restore slowness in test.sh                         | `dotnet restore` once in build.sh; build server reuse                                               |
| R16 | enum string-value (de)serialization parity                                     | Custom enum converter keyed on raw option strings; dedup v2/v3; TestSerializing covers              |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py csharp <folder>` generates a compiling C# source set.
- [ ] `uv run main.py all --csharp-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with C# included.
- [ ] `./test.sh all` (myairtable-tests) green with C# included (nine languages).
- [ ] All ten integration test files green (struct/orm crud ×3, serializing, filter, runtime,
      caching, linked, complex, special-deser).
- [ ] Unit-test parity: 16 csharp_static files matching Java's inventory; formula builder + runtime
      counts within ±5% of Rust/Java.
- [ ] Upsert + dual ID/name Fields access + DX helpers (RequireId/Value/WithView) tested.
- [ ] Generated code is idiomatic C# 12 (auto-properties, object initializers, async/await,
      exception hierarchy, no Java-isms).
