# Go Language Support — Implementation Plan v1

## 1. Overview & Goals

Add full-parity **Go** code generation to `myairtable` — the **eighth** target, alongside
Python, TypeScript, JavaScript, Rust, Swift, Kotlin, and Java. The closest structural
template is the Java target (epic `myairtable-kree`, completed 2026-06-12): same generator
architecture, same test-base semantics, same 11-feature breakdown. But the generated code
must feel **idiomatic Go 1.23** — not Java-with-`:=`: exported struct fields with
`json:"…"` tags (no getters/setters), `encoding/json` custom (un)marshalers (no Jackson
annotations), generics for the typed table layer, **errors-as-values** (typed errors +
sentinels, never panic), pointers for optional fields, `context.Context` first-arg on all
I/O, and **zero third-party runtime dependencies** (standard library only).

### User-approved design answers (2026-06-14)

| #   | Question        | Answer                                                                                                          |
| --- | --------------- | --------------------------------------------------------------------------------------------------------------- |
| 1   | context.Context | **`ctx context.Context` is the first arg of every I/O method**                                                  |
| 2   | Typed table     | **Generics `Table[T]`** in the static runtime; generator instantiates                                           |
| 3   | Error model     | **Typed errors (`errors.As`) + sentinels (`errors.Is`)**, returned                                              |
| 4   | Dependencies    | **Standard library only** (`net/http`, `encoding/json`, …); gofmt/golangci-lint are dev-tools, not runtime deps |

**Scope:**

- Generator at `src/generators/go.py` + `src/utils/write_to_go_file.py`
- Static runtime at `static/go/` (custom Airtable client — `net/http` + `encoding/json`; no
  third-party Airtable SDK, no third-party anything)
- Type mapping (`GENERIC_TO_GO`) + formula transpiler Go emitter
- Unit tests: `tests/test_generators.py` Go classes, `tests/test_formula_transpiler_go.py`,
  `tests/go_static/` Go test module (formula-builder + runtime parity, plus static-runtime
  unit tests = Java/Kotlin parity)
- Integration tests at `myairtable-tests/go/` (parity with Java/Kotlin/Swift/Rust/TS)
- CLI wiring (`main.py go` + `all --go-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):** publishing a tagged module / semantic-version git tags; `context`-free
convenience overloads; code-generated mocks; `go:generate` directives; reflection-free
hand-rolled JSON (we use `encoding/json`); any third-party module (testify, etc. — tests use
the standard `testing` package only).

## 2. Design Decisions

### 2.1 Java/Kotlin-pattern → Go idiom mapping

| Java / Kotlin construct                             | Go equivalent                                                                                                                 |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `final class AirtableClient` + HttpClient + Mutex   | `type Client struct { … }` + `*http.Client` + `sync.RWMutex`; methods take `ctx context.Context`                              |
| POJO + `@JsonProperty("fld…")` (field-access)       | `struct` with exported fields + `` `json:"fld…"` `` struct tags (§2.2.1)                                                      |
| Jackson `JsonNode` (type-erased value)              | `json.RawMessage` / `any` for the type-erased formula/runtime value (§2.2.3)                                                  |
| `sealed interface VecOrValue<T>` + custom deser     | `type VecOrValue[T any] struct{…}` + `UnmarshalJSON`/`MarshalJSON` peeking the first JSON token (§2.2.4)                      |
| `sealed interface MaybeSpecialOrError<T>`           | `type MaybeSpecialOrError[T any] struct{…}` + custom (un)marshaler                                                            |
| `enum` + `@JsonValue`/`@JsonCreator`                | typed-string constants: `type PrimarySelectOption string; const … = "…"` (§2.2.7) — marshals as a plain string                |
| `sealed AirtableException extends RuntimeException` | **Returned `error` values**: typed errors + sentinels (§2.2.6)                                                                |
| plain blocking method                               | plain blocking method taking `ctx`; cancellation honored via `ctx.Done()`                                                     |
| `AirtableRuntime` static class (V/N/S/…)            | package-level functions in `package airtable`: `V(…)`, `N(…)`, `S(…)`, … (§2.2.3)                                             |
| `PrimaryModel.f.primaryKey.eq(…)` accessor          | package-level `var PrimaryF = …`; `PrimaryF.PrimaryKey.Eq("x")` (§2.2.2, PascalCase methods)                                  |
| `_java_ident()` underscore-suffix keyword rename    | `_go_ident()` underscore-suffix rename; reserved set = 25 Go keywords + predeclared (`string`,`error`,`any`,`nil`,…) (§2.2.5) |
| `Instant` + 3-format Jackson deserializer           | `type AirtableTime struct{ time.Time }` + 3-format `UnmarshalJSON` (§2.2.6b)                                                  |
| `Duration` wire = numeric seconds                   | `type AirtableDuration time.Duration` + seconds (un)marshaler (§2.2.6b)                                                       |
| `Builder` (writable fields only) creation idiom     | **struct literal + pointer-helper funcs** `String()/Float64()/Bool()/…` (§2.2.1b) — Go has no builders/named args             |
| reified `save()/fetch()/delete()` extensions        | generator-emitted per-model methods `(m *PrimaryModel) Save(ctx)…` delegating to generic ops (§2.2.8)                         |
| `OrmTable<T>` typed CRUD                            | `Table[T]` generic struct via the pointer-constraint idiom `[T any, PT interface{ *T; Model }]` (§2.2.8)                      |
| `DictTable` raw map access                          | `DictTable` returning `Fields` (wraps `map[string]json.RawMessage`, dual ID/name access)                                      |
| flat `package myairtable`, one type per file        | flat `package airtable`, **one directory, many files** (Go forbids package≠dir) (§2.2.5)                                      |
| `AirtableView` interface + `withView`               | `type View interface{ ViewID() string }`; generated `…View` string consts implement it                                        |

### 2.2 Go-specific decisions

#### 2.2.1 Model shape: struct + json tags + pointer optionals

```go
type PrimaryModel struct {
    // Single Line Text — fldXXX (writable)
    SingleLineText *string `json:"fldXXX,omitempty"`

    // Auto Number — fldYYY (read-only / computed)
    AutoNumber *MaybeSpecialOrError[int64] `json:"fldYYY,omitempty"`

    id          string                       // unexported plumbing
    createdTime *AirtableTime                //
    client      *Client                      //
    snapshot    map[string]json.RawMessage   // dirty-tracking baseline
}
```

- **All Airtable fields are optional** → writable fields are **pointers** (`*string`,
  `*float64`, `*bool`, `*AirtableTime`, `*AirtableDuration`); list/multi-select fields are
  slices (`[]string`, `[]PrimarySelectOption`) which are already nil-able. Pointers let us
  distinguish "absent" from "zero/cleared" — essential for Airtable PATCH semantics.
- **`json:"fld…"` tags carry field IDs** (mirrors `@JsonProperty` raw = field ID). Computed
  and writable fields look identical at the type level (Go has no read-only fields); the
  **read-only contract is enforced only by the payload builders** (`toCreateFields`/
  `dirtyFields` emit writable field IDs only). Documented; covered by offline tests.
- **Decoding** uses `encoding/json` directly into the struct. **Encoding for create/update
  is hand-rolled** (writable-only `map[string]json.RawMessage`) — the struct's own
  `MarshalJSON` is NOT used for payloads (parity with every other language).
- Dirty tracking: unexported `snapshot map[string]json.RawMessage` (lowercase → never
  serialized) + diff in `dirtyFields()`. Port of Java `@JsonIgnore` snapshot.
- `int64` for auto-number/count; **`float64` for every Airtable `number`** (tests use `42.0`).

#### 2.2.1b Creation idiom: struct literal + pointer helpers

Go has no builders or named/default args. The idiomatic creation path is a struct literal.
Pointer optionals would force ugly `&[]string{…}[0]` literals, so the runtime ships
**pointer-helper constructors** (the AWS-SDK-v1 `aws.String` pattern):

```go
p := PrimaryModel{ PrimaryKey: airtable.String("Go CRUD PKOnly 123") }
p.Email = airtable.String("x@y.z")        // post-construct mutation
```

`func String(s string) *string`, `Float64`, `Int64`, `Bool`, `Time(time.Time) *AirtableTime`,
`Duration(time.Duration) *AirtableDuration`. These are THE creation idiom in integration
tests (the Go analog of Java's mandated Builder). No separate `Create…` type (cross-language
decision stands).

#### 2.2.2 Filter DSL: PascalCase `Eq`/`Neq`

Go has no `equals` footgun (Kotlin/Java's reason for `eq`/`neq`), but **method names are
PascalCase** in Go: `Eq`, `Neq`, `Contains`, `StartsWith`, `EndsWith`, `GreaterThan`,
`LessThan`, `IsEmpty`, `IsNotEmpty`, etc. — same semantics as other languages, Go casing.
Accessor is a package-level value (Go has no static fields): generator emits
`var PrimaryF = primaryFilters{ PrimaryKey: …, … }`; usage `PrimaryF.PrimaryKey.Eq("x")`.

#### 2.2.3 Type-erased value = `any` / `json.RawMessage`; coercions are package funcs

The formula runtime operates on `any` (decoded JSON: `nil`, `bool`, `float64`, `string`,
`[]any`, `map[string]any`). Unlike Java (statics on `AirtableRuntime`), Go uses
**package-level functions** in `package airtable`: `V`, `N`, `S`, `A`, `AN`, `AS`, `D`,
`IsTruthy`, plus the ~80 formula functions. The transpiler's `_runtime` qualifier is empty
(bare calls, same package) **or** a package selector if the runtime lives in a sub-package
(decided in F1: single flat package → bare calls like TS/Python's `F`-less style, OR a
short alias). `V` boxes any Go value into the `any` representation used by `toCreateFields`.

#### 2.2.4 Generic sum types via first-token peek (the F1.13 gate)

`encoding/json` analog of Jackson's `readTree` peek: custom `UnmarshalJSON` on the generic
type inspects the raw bytes, then unmarshals the payload into the captured type parameter.

```go
type VecOrValue[T any] struct { multiple bool; single T; list []T }
func (v *VecOrValue[T]) UnmarshalJSON(b []byte) error {
    if len(bytes.TrimSpace(b)) > 0 && bytes.TrimSpace(b)[0] == '[' { /* → list */ }
    /* else → single */
}
```

- `VecOrValue[T]`: leading `[` → `Multiple([]T)`; else `Single(T)`.
- `MaybeSpecialOrError[T]`: object with `"specialValue"` → `Special`; with `"error"` →
  `Error`; else → `Value(T)`.
- **Nested `VecOrValue[MaybeSpecialOrError[T]]`** works because the element type
  `MaybeSpecialOrError[T]` itself implements `json.Unmarshaler`; `encoding/json` dispatches
  to it via reflection on the concrete instantiated type. **This is the single biggest Go
  risk** (generics + `encoding/json` + nested Unmarshalers) and the F1.13 prototype gate
  must prove decode **and** encode round-trips for: `MaybeSpecialOrError[string]`,
  `[float64]`, `[AirtableTime]`, `VecOrValue[string]`, and the nested
  `VecOrValue[MaybeSpecialOrError[string]]`, on a real struct field — before any templating.
- DX accessors: `func (m MaybeSpecialOrError[T]) Value() (T, bool)`;
  `func (v VecOrValue[T]) Values() []T`; `CleanValues()` for the nested case.

#### 2.2.5 Flat single package; one directory

Go forbids `package != directory`, so the Java multi-subdir-but-flat-package trick is
impossible. **All generated + static files live in ONE directory** (`go/output/`) under
**`package airtable`** (short, lowercase, idiomatic — flagged minor; could be `myairtable`).
No import cycles (same package). Files are split by concern (`model_primary.go`,
`options_primary.go`, `fields_primary.go`, `filters_primary.go`, `airtable.go`, + static
files). Integration tests import this package from a sibling directory (`go/tests/`,
`package tests`). `reset_folder` wipes & repopulates `output/` (static copied + dynamic
written) each run; tests outside `output/` are untouched.

#### 2.2.6 Errors: typed + sentinels, returned

```go
var ( ErrNotFound = errors.New("airtable: record not found")
      ErrMissingCredentials = errors.New("airtable: missing credentials") )
type APIError struct { StatusCode int; Type, Message string }      // errors.As
type RateLimitError struct { RetryAfter time.Duration }            // errors.As
type DecodingError struct { Err error }                            // Unwrap → errors.As/Is
type HTTPError struct { StatusCode int; Body string }
```

All I/O returns `(T, error)`. `RateLimitError` carries `RetryAfter`; client retry inspects
it internally. Callers use `errors.Is(err, ErrNotFound)` / `errors.As(err, &apiErr)`.

#### 2.2.6b Date / Duration / numbers

- **Date**: `type AirtableTime struct{ time.Time }` with `UnmarshalJSON` trying, in order:
  RFC3339 w/ fractional → RFC3339 → date-only `2006-01-02` → midnight UTC. `MarshalJSON`
  emits RFC3339. Models use `*AirtableTime` (plain `time.Time` can't parse date-only).
- **Duration**: `type AirtableDuration time.Duration`; wire = **numeric seconds** (locked by
  Swift/Kotlin/Java live verification). Default `time.Duration` JSON would be int64 nanos —
  wrong; custom (un)marshaler converts seconds↔Duration. F1.13 asserts numeric-seconds.
- **`EXP(1.0)` ULP**: JVM `Math.exp(1.0)` is one ULP above V8's `Math.E`; Java/Kotlin pinned
  it. **Go's `math.Exp(1.0)` may differ from both** — verify-first; pin `EXP(1.0)` to
  `math.E` if the live API round-trip mismatches (runtime parity test).

#### 2.2.7 Select options: typed-string constants

```go
type PrimarySingleSelectOption string
const ( PrimarySingleSelectOptionFoo PrimarySingleSelectOption = "Foo"
        PrimarySingleSelectOptionBar PrimarySingleSelectOption = "Bar" )
```

Marshals/unmarshals as a plain string (the underlying type IS `string`) — no custom
(un)marshaler needed. Const names PascalCase, prefixed by the type for package uniqueness;
collisions deduped with a numeric suffix (parity with `_choice_to_entry`).

#### 2.2.8 Table layer: generics + per-model fluent methods

- Static `Table[T]` via the **pointer-constraint idiom** so `new(T)`-then-decode works and
  the `Model` plumbing methods (pointer receivers) are visible:
  ```go
  type Model interface { TableID() string; toCreateFields() map[string]json.RawMessage; … }
  type Table[T any, PT interface{ *T; Model }] struct { client *Client; tableID string }
  func (t Table[T,PT]) Get(ctx context.Context, id string) (PT, error) { … }
  ```
  (Exact constraint shape is an F1.13 gate.) Generated `Airtable` struct exposes
  `Primary Table[PrimaryModel, *PrimaryModel]` etc. Includes `Upsert` (parity with Rust/Java).
- **`DictTable`** for raw `Fields` access (dual ID/name lookup), mirroring `Table`'s API.
- Go methods can't add type params, so **per-model fluent CRUD is generator-emitted**:
  `func (m *PrimaryModel) Save(ctx context.Context) error { return modelSave(ctx, m) }`
  (likewise `Fetch`, `Delete`), delegating to generic free functions `modelSave[T]…` in the
  static runtime (the Go analog of Java `ModelOps`). Model holds the attached `client` +
  table id; `requireID`/`requireClient` return errors when unset.

#### 2.2.9 URL encoding verify-first

`net/url`: `url.Values.Encode()` encodes space→`+` and `+`→`%2B` (query). Like Java's
`URLEncoder`, this is **likely** correct for `filterByFormula=LEN({f})+1`, but it is an
inference — the **verify-first spike** must confirm a `LEN({f})+1` filter round-trips against
the real base. **Path segments** (table names with spaces) need `url.PathEscape` (→ `%20`),
never query encoding. Both pinned by a URL-encoding unit test.

#### 2.2.10 Formatting & lint

- **`gofmt`** ships with the toolchain and is deterministic. Generated output is emitted
  **gofmt-clean by construction**; checks verify via `gofmt -l output/` (must print nothing)
  — stronger than Java's "never touch generated output," and free. Unused imports are a
  **compile error** in Go, so the writer's import accumulator must be exact.
- **`go vet`** always; **`golangci-lint`** behind a `command -v` warn-skip guard (like
  ktlint/google-java-format). Initialism lint (`Id`→`ID`) is NOT enforced on generated code
  (field names are arbitrary Airtable strings); hand-written `static/go` follows Go casing.

### 2.3 Other settled choices

| Decision            | Value                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| Go version          | **Go 1.23+** in `go.mod` (1.22 floor for the generics patterns)                                |
| Test framework      | standard library **`testing`** (`t.Run`, `t.Fatalf`) — no testify                              |
| Integration phasing | sequential within a file via ordered `t.Run` subtests; package-level setup in `TestMain`       |
| Test parallelism    | NO `t.Parallel()` across CRUD files; distinct primary keys per file (`"Go StructCrud … {ts}"`) |
| File naming         | `snake_case.go` (Go convention); exported identifiers PascalCase via `name_pascal()`           |
| Linked records      | raw `[]string` record IDs; resolve via `airtable.Secondary.Get(ctx, id)`                       |
| go.mod (tests repo) | hand-written; `output/` is an importable sub-package                                           |
| Doc comments        | `// …` line comments (Go has no block-doc HTML hazard — drop `_javadoc_escape` entirely)       |
| Static unit tests   | `tests/go_static/` module (symlinks `static/go/*.go`, Swift precedent) — verify-first in F1    |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/go.py                  # NEW ~900 LOC (mirrors java.py; fewer files — no enums,
                                      #   no getters/setters, struct tags instead of annotations)
src/utils/write_to_go_file.py         # NEW WriteToGoFile: package decl, IMPORT ACCUMULATOR
                                      #   (exact — unused import = compile error), // doc comments,
                                      #   struct open/close, struct-FIELD-WITH-JSON-TAG emitter,
                                      #   interface emitter, typed-string-const emitter,
                                      #   _go_ident() (_-suffix; 25 keywords + predeclared),
                                      #   _go_string_literal(), _choice_to_const()
src/utils/type_mapper.py              # MOD: GENERIC_TO_GO; "go" in Language literal (:341);
                                      #   LANGUAGE_CONFIGS "go" (list_fmt="[]{0}", union_fmt,
                                      #   unknown); map_go_type(); apply_go_computed_wrapping();
                                      #   is_already_list "go" (startswith "[]"); map_types()
                                      #   first-pass go lines (:~221/:~228); apply_disambiguated_type
                                      #   go branch (:~884)
src/utils/write_to_file.py            # MOD: "go" in language Literal (:49); add "go" to the
                                      #   //-comment header case (:74)
src/meta.py                           # MOD: _go_type PrivateAttr (:383); go_type property (:~610)
src/formulas/formula_transpiler.py    # MOD: "go" in Language literal (:21); _self (:323) →
                                      #   receiver var; _runtime (:326); go arm (or fall-through
                                      #   tuple membership) in ALL ~44 guarded emit sites
                                      #   (enumerated §3.4): NumberLiteral/StringLiteral, field
                                      #   ref, fn dispatch, every _emit_fn_*, _emit_str/_emit_num,
                                      #   _emit_binary_op/_emit_unary_op, _go_ident renaming
main.py                               # MOD: import generate_go (:11-area); `go` command (:~230);
                                      #   all() go_folder option (:~371) + if go_folder block (:~436)
checks.sh                             # MOD: Go section (go build + go vet + gofmt -l guard +
                                      #   golangci-lint command -v guard; cd tests/go_static; go test)
static/go/                            # NEW static runtime (§4)
tests/test_generators.py             # MOD: TestGo* classes; BOTH make_test_base __pydantic_private__
                                      #   dicts gain "_go_type": None (:86-area; :478-area which is
                                      #   already missing rust/swift/java keys — audit)
tests/test_formula_transpiler_go.py   # NEW (~45 cases; mirror Java/Kotlin/Swift twins)
tests/go_static/                      # NEW Go module (symlinks static/go/*.go; package airtable)
  ├── go.mod
  └── *_test.go                       # static-runtime unit tests = Java/Kotlin parity (below)
      ├── pojo_model_test.go          # F1.13 prototype gate (§2.2.1/2.2.4/2.2.5/2.2.6b/2.2.8)
      ├── harness_test.go
      ├── query_build_test.go
      ├── exception_decoding_test.go  # error decode / errors.As / errors.Is
      ├── cache_store_test.go
      ├── client_cache_policy_test.go
      ├── client_hardening_test.go
      ├── client_url_encoding_test.go
      ├── date_decoding_test.go
      ├── dx_helpers_test.go          # Value()/CleanValues()/requireID/View
      ├── special_error_decoding_test.go
      ├── fields_dual_access_test.go
      ├── value_coercion_test.go
      ├── table_bounded_ops_test.go
      ├── formula_test.go             # ~80 builder cases (Rust parity)
      └── airtable_runtime_test.go    # ~167 runtime cases (Rust parity)
```

### 3.2 Generated output (per run)

```
go/output/                            # ONE directory, package airtable; generator emits NO go.mod
├── airtable.go                       # Airtable struct: BASE_ID, Client, per-table fields, ctors
├── model_{table}.go                  # struct + json tags + per-model Save/Fetch/Delete + evaluate*
├── options_{table}.go                # typed-string-const groups (one per select field)
├── fields_{table}.go                 # field ID/name consts, id↔name maps, allIds, View consts
├── filters_{table}.go                # formula-builder accessors + package-level var {Table}F
└── <static files copied from static/go/>
```

All files declare `package airtable` (§2.2.5).

### 3.3 Test repo (`myairtable-tests`)

```
go/
├── go.mod                            # HAND-WRITTEN (module path; Go 1.23; NO requires)
├── output/                           # regenerated by build.sh (package airtable)
└── tests/                            # package tests; imports <module>/output
    ├── main_test.go                  # TestMain: .env walker + Airtable factory + primaryKey()
    ├── harness_test.go               # smoke: VERSION reachable
    ├── struct_crud_via_table_test.go
    ├── orm_crud_via_table_test.go
    ├── orm_crud_via_model_test.go
    ├── serializing_test.go
    ├── filter_by_formula_test.go
    ├── runtime_formulas_test.go
    ├── caching_test.go
    ├── linked_records_test.go
    ├── complex_properties_test.go
    └── special_error_deser_test.go
build.sh                              # MOD: --go-folder ./go/output
test.sh                               # MOD: go case (go test -run …) + add `go` to the all loop
checks.sh                             # MOD: Go block (go build ./... + gofmt -l + golangci-lint guard)
```

`test.sh` go case:

```bash
elif [ "$LANG_ARG" = "go" ]; then
    case "$SUITE" in
        --all)     TEST_CMD="(cd go && go test -v ./...)" ;;
        --crud)    TEST_CMD="(cd go && go test -v -run 'TestStructCrudViaTable|TestOrmCrudViaTable|TestOrmCrudViaModel' ./...)" ;;
        --json)    TEST_CMD="(cd go && go test -v -run 'TestSerializing' ./...)" ;;
        --filter)  TEST_CMD="(cd go && go test -v -run 'TestFilterByFormula' ./...)" ;;
        --runtime) TEST_CMD="(cd go && go test -v -run 'TestRuntimeFormulas' ./...)" ;;
        --cache)   TEST_CMD="(cd go && go test -v -run 'TestCaching' ./...)" ;;
    esac
```

## 4. Static Runtime Contract (`static/go/`, ~25 files, ~4,000 LOC)

| File                            | Contents                                                                                                                                                                                                 |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `errors.go`                     | sentinels (`ErrNotFound`, `ErrMissingCredentials`) + typed errors (`APIError`, `RateLimitError`, `HTTPError`, `DecodingError`) w/ `Error()`/`Unwrap()` (§2.2.6)                                          |
| `client.go`                     | `Client` struct, `*http.Client`, bearer auth, 429 retry/backoff (ctx-aware), all record endpoints, owns cache, chunk-of-10 batching; path-vs-query encoding (§2.2.9 verify-first)                        |
| `cache.go`                      | TTL cache behind `sync.RWMutex`; per-table wipe; `InvalidateAll()`                                                                                                                                       |
| `json.go`                       | shared (un)marshal helpers; `V()` boxing; `AirtableTime`/`AirtableDuration` (un)marshalers (§2.2.6b)                                                                                                     |
| `model.go`                      | `Model` interface (TableID, toCreateFields, toRecord, snapshot/dirty, id/createdTime/client plumbing, isNew); generic `modelSave/modelFetch/modelDelete` helpers backing emitted fluent methods (§2.2.8) |
| `record.go`                     | generic `Record[T]` envelope (id, createdTime, fields)                                                                                                                                                   |
| `fields.go`                     | `Fields` wraps `map[string]json.RawMessage`; dual ID/name `Get`/`Set` (ID-first, name fallback)                                                                                                          |
| `dict_table.go`                 | raw CRUD returning `Fields`; mirrors `Table` API                                                                                                                                                         |
| `table.go`                      | generic `Table[T,PT]` — typed CRUD + `Upsert`, batching, cache invalidation (§2.2.8)                                                                                                                     |
| `query.go`                      | `Query`: filter, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldID; `toParams()`; `WithView`                                                                                               |
| `view.go`                       | `type View interface{ ViewID() string }`                                                                                                                                                                 |
| `sort.go`                       | `Sort` spec + `SortDirection` consts                                                                                                                                                                     |
| `helpers.go`                    | pointer helpers `String/Float64/Int64/Bool/Time/Duration` (§2.2.1b)                                                                                                                                      |
| `vec_or_value.go`               | `VecOrValue[T]` + custom (un)marshaler + `Values()` (§2.2.4)                                                                                                                                             |
| `maybe_special_or_error.go`     | `MaybeSpecialOrError[T]` + custom (un)marshaler + `Value()`; `SpecialNumber`, `ErrorValue` (§2.2.4)                                                                                                      |
| `formula.go`                    | `Formula` type + combinators (And/Or/Not/Xor) + base field helpers                                                                                                                                       |
| `formula_fields.go`             | per-type formula builders (Text/Number/Date/Boolean/Select/MultiSelect/Lookup/ID/Attachment) using Eq/Neq                                                                                                |
| `formula_date.go`               | date-formula sub-DSL (operand/literal/comparison)                                                                                                                                                        |
| `runtime.go`                    | ~80 formula functions + coercions `V/N/S/A/AN/AS/D/IsTruthy` (§2.2.3); EXP pin (§2.2.6b)                                                                                                                 |
| `attachment.go`                 | `Attachment` (+ `Thumbnails`/`Thumbnail`)                                                                                                                                                                |
| `collaborator.go` / `button.go` | data carriers                                                                                                                                                                                            |
| `runtime_info.go`               | `VERSION` constant                                                                                                                                                                                       |

(Several Java files collapse in Go: no separate `AirtableJson`/`AirtableJacksonModule`
mapper trio; no separate Serializer/Deserializer files — custom marshalers live with their
types; no `ModelOps`/`AirtableModel` split — both in `model.go`.)

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"go"` in `write_to_file.py` language Literal (:49) + `//`-comment header case (:74).
- 1.2 `write_to_go_file.py` (`WriteToGoFile` + import accumulator + `_go_ident` keyword set +
  `_go_string_literal` + `_choice_to_const` + struct-field-with-tag emitter).
- 1.3 Type wiring — ALL: `GENERIC_TO_GO`; `"go"` in type_mapper Literal; `LANGUAGE_CONFIGS`
  entry; `map_go_type()`; `apply_go_computed_wrapping()`; `is_already_list` go; `map_types()`
  first-pass go lines; `apply_disambiguated_type()` go branch; meta.py `_go_type` +
  property; BOTH `make_test_base` dicts gain `"_go_type": None` (audit the second dict's
  pre-existing missing keys).
- 1.4 `main.py go` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--go-folder`).
- 1.6 `tests/go_static/` Go module (go.mod; symlink `static/go/*.go`; verify-first §2.2.5).
- 1.7 `myairtable-tests/go/` skeleton (hand-written go.mod; `output/` package; `tests/` package).
- 1.8 `myairtable-tests/build.sh`: `--go-folder`.
- 1.9 `myairtable-tests/test.sh`: go case (§3.3) AND add `go` to the `all` loop + exec path.
- 1.10 `myairtable-tests/checks.sh`: Go block (go build + gofmt -l + golangci-lint guard).
- 1.11 `myairtable/checks.sh`: Go section (go test in tests/go_static; gofmt/vet; warn-skip w/o go).
- 1.12 **Prototype gate** `pojo_model_test.go` proving ALL risky foundations before templating:
  (a) struct decode of `json:"fld…"` field-ID keys incl. computed pointer fields; (b) generic
  sum-type round-trips — `MaybeSpecialOrError[string|float64|AirtableTime]`,
  `VecOrValue[string]`, nested `VecOrValue[MaybeSpecialOrError[string]]` — decode AND encode;
  (c) `AirtableDuration` encodes as numeric seconds (not nanos); (d) snapshot + writable-only
  payload builder; (e) the `Table[T,PT]` pointer-constraint idiom compiles and `Get` decodes
  into `new(T)`.

**Exit**: `uv run main.py go <folder>` exits 0 (stub ok); `go build ./...` compiles both
modules; prototype green; both checks.sh and test.sh run their go sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `errors.go` (sentinels + typed). 2.2 value/sum types (`vec_or_value.go`,
  `maybe_special_or_error.go`, `record.go`, `attachment.go`, `collaborator.go`, `button.go`,
  `sort.go`, `view.go`, `AirtableTime`/`AirtableDuration` in `json.go`).
- 2.3 `client.go` — starts with the URL-encoding verification spike (§2.2.9).
- 2.4 `query.go` incl. `WithView`; 2.5 `fields.go`; 2.6 `dict_table.go`; 2.7 `cache.go`
  skeleton (API + mutex; TTL/LRU deferred to F9).
- 2.8 `runtime.go` coercion funcs (`V/N/S/A/AN/AS/D/IsTruthy`) + `helpers.go` pointer ctors.
- 2.9 Unit tests: query_build, exception_decoding, fields_dual_access, date_decoding,
  special_error_decoding, value_coercion, client_url_encoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration test ASAP

- 3.1 `generate_go()` entry + static copy (exclude runtime.go / formula files per flags;
  exclude `*_test.go` + `go.mod` from copy).
- 3.2 `write_options()` — typed-string-const group per select field; dedup collisions.
- 3.3 `write_field_types()` — `fields_{table}.go` (ID/name consts, id↔name maps, allIds) +
  `View` consts implementing `View`.
- 3.4 `write_tables()` (dict accessor only) + 3.5 `write_main()` — `Airtable` struct +
  constructors `New(client)` / `NewWithKey(apiKey, baseID)` / `…cacheSeconds`.
- 3.6 Offline unit tests (`TestGo*` content assertions; no `go build` shell-out).
- 3.7 **Integration**: `struct_crud_via_table_test.go` green against the real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `model.go` (`Model` interface + generic ops); 4.2 `table.go` generic `Table[T,PT]`
  incl. `Upsert`.
- 4.3 `write_models()` — struct + json-tag fields + pointer optionals; snapshot dirty
  tracking; per-model `Save/Fetch/Delete`; doc comments per field; `evaluate*` methods when
  runtime=True.
- 4.4 `write_tables()` ORM accessor (generic instantiation).
- 4.5 Unit tests `TestGoComputedFields`: computed = pointer + excluded from payload builders;
  writable = in payload; json tags + wrapper types present; evaluate methods gated on runtime.
- 4.6 Offline `serializing_test.go` (8 parity cases).
- 4.7 **Integration**: orm_crud_via_table (pk-only, all-simple, upsert insert/update,
  111-record batch, field selection, maxRecords, invalid-ID error), orm_crud_via_model
  (Save/Fetch/Delete).

### Feature 5 — Complex Field Types [P2]

- 5.1 attachment upload (URL-based, TS parity); 5.2 collaborator; 5.3 computed
  `MaybeSpecialOrError` end-to-end; 5.4 button decode; 5.5 duration round-trip magnitude.
- 5.6 **Integration**: complex_properties_test.go + complex CRUD sections.
- 5.7 **Integration**: special_error_deser_test.go.

### Feature 6 — Linked Records [P2]

- 6.1 Generator: raw `[]string` record-ID fields.
- 6.2 **Integration**: linked_records_test.go (resolution via `airtable.Secondary.Get`).

### Feature 7 — Formula Builders [P2]

- 7.1 formula field types (Eq/Neq §2.2.2); 7.2 combinators; 7.3 `write_formula_helpers()` →
  `filters_{table}.go` + package-level `var {Table}F`.
- 7.4 Unit tests `formula_test.go` (~80 cases: combinators 7, id 4, text 19, single-select 4,
  multi-select 4, number 9, bool 4, date 14, attachment 3, lookup 7 — Rust categories).
- 7.5 **Integration**: filter_by_formula_test.go.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler wiring per §3.4 (all ~44 guarded sites; `_runtime`/`_self`; `_go_ident`).
  Evaluate methods return `any`.
- 8.2–8.8 `runtime.go` groups: math (incl. EXP pin), logic, string, date (time pkg), array,
  regex, coercions.
- 8.9 Generator wires `evaluate*` methods on models.
- 8.10 `tests/test_formula_transpiler_go.py` (~45 cases).
- 8.11 `airtable_runtime_test.go` ~167 cases.
- 8.12 **Integration**: runtime_formulas_test.go.

### Feature 9 — Caching [P3]

- 9.1 cache TTL/LRU/per-table wipe; 9.2 cached read paths; 9.3 mutation invalidation;
  9.4 `InvalidateAllCaches()` + per-table.
- 9.5 **Integration**: caching_test.go (~10 scenarios, Rust parity).

### Feature 10 — Serialization (integration portion) [P3]

- 10.1 network-bound serializing cases: linked-record ID arrays, createdTime round-trip,
  unsaved-id behavior.

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 file-by-file test diff vs Java/Kotlin/Swift/Rust/Python/TS; close gaps.
- 11.2 `./checks.sh` both repos green; 11.3 `./test.sh all` green (eight languages);
  11.4 `main.py all` with go alongside others; 11.5 README updates (both repos).

## 3.4 Transpiler integration sites (the ~44 guarded blocks)

Every `kotlin`/`java` arm in `formula_transpiler.py` needs a `go` arm (or `"go"` added to a
`return None` fall-through tuple where Go routes through its runtime). Verified site list:
NumberLiteral (339), StringLiteral (354), field ref (383), fn dispatch (458),
record*id/true/false/blank/not/and/or/xor/if/ifs/switch/countall (514–949), the many
`return None` math/string/regex guards (642–1061: len, str-method, encode-url, int, abs,
sqrt, exp, log10, power, mod, regex-extract, min, max, sum, round, concatenate, rept,
regex-match, regex-replace, today, now, datetime-parse, date-part), `_emit_str` (1124),
`_emit_num` (1150), `_emit_binary_op` (1210), `_emit_unary_op` (1303). `test_formula*
transpiler_go.py` pins each.

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

| #   | Risk                                                          | Mitigation                                                                        |
| --- | ------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| R1  | Generics + `encoding/json` can't decode nested sum types      | §2.2.4 first-token peek + per-type Unmarshaler; F1.12 nested gate (decode+encode) |
| R2  | `Table[T,PT]` pointer-constraint idiom won't compile / decode | F1.12(e) compile + `Get` decode proof before templating                           |
| R3  | Go forbids package≠dir (Java's flat trick fails)              | §2.2.5 single flat dir/package; tests in sibling package                          |
| R4  | Unused imports = compile error (generated code won't build)   | exact import accumulator in `write_to_go_file.py`; `go build` in CI               |
| R5  | Duration default JSON = nanoseconds (not seconds)             | `AirtableDuration` custom marshaler; F1.12(c) numeric-seconds assert              |
| R6  | `time.Time` can't parse date-only Airtable dates              | `AirtableTime` 3-format Unmarshaler; date_decoding_test                           |
| R7  | URL encoding (`+`, spaces, path vs query)                     | §2.2.9 verify-first spike; client_url_encoding_test; live round-trip              |
| R8  | `math.Exp(1.0)` mismatch vs Airtable                          | verify-first; pin EXP(1.0) to math.E if needed; runtime parity test               |
| R9  | Go keyword/predeclared collisions (no escape)                 | `_go_ident()` `_`-suffix rename; unit tests incl. `string`/`error`/`any`          |
| R10 | Transpiler emits Java-isms (qualified calls, `NullNode`)      | §3.4 explicit enumeration; test_formula_transpiler_go.py                          |
| R11 | Disambiguated lookup/rollup skip Go types                     | F1.3 explicit `map_types` + `apply_disambiguated_type` tasks + test               |
| R12 | go_static symlink module flaky                                | verify-first F1.6; fallback: in-place `static/go/*_test.go` + go.mod              |
| R13 | Pointer-optional ergonomics balloon test verbosity            | pointer-helper ctors (§2.2.1b); accept (idiomatic for optional JSON)              |
| R14 | `float64` equality in tests                                   | numbers-are-float64 documented; tests use `42.0`                                  |
| R15 | golangci-lint initialism noise on generated names             | never lint generated; hand-written static follows Go casing                       |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py go <folder>` generates a compiling Go package (`go build` clean, `gofmt -l` empty).
- [ ] `uv run main.py all --go-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Go included.
- [ ] `./test.sh all` (myairtable-tests) green with Go included (eight languages).
- [ ] All eleven integration test files green (struct/orm crud ×3, serializing, filter,
      runtime, caching, linked, complex, special-deser).
- [ ] Unit-test parity: go_static files matching Java/Kotlin inventory; formula builder ~80 +
      runtime ~167 within ±5% of Rust/Java.
- [ ] Upsert + dual ID/name Fields access + DX helpers (Value/CleanValues/View) tested.
- [ ] Generated code is idiomatic Go (struct tags, pointer optionals, generics, errors-as-values,
      no Java-isms, gofmt-clean).

```

```
