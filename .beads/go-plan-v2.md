# Go Language Support — Implementation Plan v2

> **Changes from v1 (plan-critic round, 2026-06-14):**
>
> - **CRIT-1/CRIT-2 (transpiler wiring):** v1 implied an empty `_runtime` works with the
>   existing call sites — it does not (Go would fall to `_runtime="F"` → `F.LOWER(...)` and
>   `_self="this"` → `this.field`, both invalid Go). v2 locks the real model: Go's runtime
>   value is **native `any`** (like TS/Python), NOT a boxed node (Java/Kotlin); Go uses
>   **bare same-package runtime calls**; `_self="m"`; and — newly identified — **Go has no
>   ternary**, so IF/IFS/SWITCH emit runtime _functions_, not inline `?:`. Transpiler section
>   rewritten (§3.4) with an accurate, smaller Go-specific arm count.
> - **CRIT-3 (static unit-test module):** dropped the fragile `tests/go_static` symlink
>   module; unit tests now live **in-place** as `static/go/*_test.go` with an excluded
>   `static/go/go.mod` (§2.2.5b) — no symlinks, no module collision.
> - **CRIT-4 (generic JSON decode):** F1.12 gate strengthened to a _runtime_ proof that
>   `json.Unmarshal` dispatches to a type-parameter's pointer-receiver `UnmarshalJSON` for
>   nested `VecOrValue[MaybeSpecialOrError[T]]` (§2.2.4).
> - **HIGH fixes:** explicit `apply_disambiguated_type` Go line; SWITCH/IFS/COUNTALL/RECORD_ID
>   Go runtime signatures pinned (§4); module path for `myairtable-tests/go` locked (§3.3);
>   the second `make_test_base` dict's missing `_rust_type`/`_swift_type`/`_java_type` keys
>   added alongside `_go_type` (F1.3); `computed_union_fmt` decision (Go uses the apply-fn
>   path, no config field) (§2.2.x, verified); `ID()` accessor resolves the unexported-id vs
>   RECORD_ID() tension (§2.2.8).
> - **MED fixes:** import accumulator must emit **alphabetically sorted** imports (gofmt) (R16);
>   formula-builder test count reconciled to **test_formula.rs exactly** (§5 F7.4); Go version
>   floor clarified (1.21+; 1.23 recommended) (§2.3); file table notes inlined Thumbnails /
>   error-envelope / `runtime_info.go` (§4).

## 1. Overview & Goals

Add full-parity **Go** code generation to `myairtable` — the **eighth** target, after
Python, TypeScript, JavaScript, Rust, Swift, Kotlin, and Java. The closest structural
template is the Java target (epic `myairtable-kree`, 2026-06-12): same generator
architecture, same test-base semantics, same 11-feature breakdown. But the generated code
must feel **idiomatic Go** — not Java-with-`:=`: exported struct fields with `json:"…"` tags
(no getters/setters, no annotations), `encoding/json` custom (un)marshalers, generics for the
typed table layer, **errors-as-values** (typed errors + sentinels, never panic), pointers for
optional fields, `context.Context` first-arg on all I/O, and **zero third-party runtime
dependencies** (standard library only).

### User-approved design answers (2026-06-14)

| #   | Question        | Answer                                                                   |
| --- | --------------- | ------------------------------------------------------------------------ |
| 1   | context.Context | **`ctx context.Context` is the first arg of every I/O method**           |
| 2   | Typed table     | **Generics `Table[T,PT]`** in the static runtime; generator instantiates |
| 3   | Error model     | **Typed errors (`errors.As`) + sentinels (`errors.Is`)**, returned       |
| 4   | Dependencies    | **Standard library only**; gofmt/go vet/golangci-lint are dev-tools      |

**Scope:** generator `src/generators/go.py` + `src/utils/write_to_go_file.py`; static runtime
`static/go/` (custom client — `net/http` + `encoding/json`); type mapping (`GENERIC_TO_GO`) +
transpiler Go emitter; unit tests (`tests/test_generators.py` Go classes,
`tests/test_formula_transpiler_go.py`, in-place `static/go/*_test.go`); integration tests
`myairtable-tests/go/`; CLI wiring (`main.py go` + `all --go-folder`); `checks.sh` (both
repos), `myairtable-tests/{build,test}.sh`.

**Non-goals (v1):** publishing a tagged/versioned module; `context`-free overloads; generated
mocks; `go:generate`; any third-party module (tests use stdlib `testing` only).

## 2. Design Decisions

### 2.1 Java/Kotlin → Go idiom mapping

| Java / Kotlin                          | Go                                                                                                         |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `final class AirtableClient` + Mutex   | `type Client struct{…}` + `*http.Client` + `sync.RWMutex`; methods take `ctx context.Context`              |
| POJO + `@JsonProperty("fld…")`         | `struct` with exported fields + `` `json:"fld…,omitempty"` `` tags (§2.2.1)                                |
| Jackson `JsonNode` (type-erased)       | **native `any`** (decoded JSON: nil/bool/float64/string/[]any/map) — TS/Python model, NOT boxed (§2.2.3)   |
| `sealed VecOrValue<T>` + custom deser  | `type VecOrValue[T any] struct{…}` + first-token-peek `UnmarshalJSON`/`MarshalJSON` (§2.2.4)               |
| `sealed MaybeSpecialOrError<T>`        | `type MaybeSpecialOrError[T any] struct{…}` + custom (un)marshaler                                         |
| `enum` + `@JsonValue`/`@JsonCreator`   | typed-string consts `type …Option string; const … = "…"` (§2.2.7) — marshals as plain string               |
| `sealed AirtableException`             | **returned `error`**: typed + sentinels (§2.2.6)                                                           |
| `AirtableRuntime` statics (V/N/S/…)    | **package-level funcs**, called **bare** (same package): `V(…)`, `N(…)`, `S(…)` (§2.2.3, §3.4)             |
| `PrimaryModel.f.primaryKey.eq(…)`      | package var `var PrimaryF = …`; `PrimaryF.PrimaryKey.Eq("x")` (PascalCase, §2.2.2)                         |
| `_java_ident()` keyword rename         | `_go_ident()` `_`-suffix; set = 25 keywords + predeclared (`string`,`error`,`any`,`nil`,`true`,…) (§2.2.5) |
| `Instant` 3-format deser               | `type AirtableTime struct{ time.Time }` + 3-format `UnmarshalJSON` (§2.2.6b)                               |
| `Duration` wire = seconds              | `type AirtableDuration time.Duration` + seconds (un)marshaler (§2.2.6b)                                    |
| `Builder` creation idiom               | **struct literal + pointer helpers** `String()/Float64()/Bool()/…` (§2.2.1b)                               |
| reified `save/fetch/delete`            | generator-emitted `(m *PrimaryModel) Save(ctx) error` → generic ops in `model.go` (§2.2.8)                 |
| `OrmTable<T>`                          | generic `Table[T any, PT interface{ *T; Model }]` (pointer-constraint idiom, §2.2.8)                       |
| flat `package myairtable`, 1 type/file | flat `package airtable`, **one directory, many files** (Go forbids package≠dir) (§2.2.5)                   |
| `AirtableView` + `withView`            | `type View interface{ ViewID() string }`; generated `…View` consts implement it (LOW: name-collision note) |

### 2.2 Go-specific decisions

#### 2.2.1 Model shape: struct + json tags + pointer optionals

```go
type PrimaryModel struct {
    SingleLineText *string                      `json:"fldXXX,omitempty"` // writable
    AutoNumber     *MaybeSpecialOrError[int64]  `json:"fldYYY,omitempty"` // computed / read-only
    LinkedItems    []string                     `json:"fldZZZ,omitempty"` // linked record IDs

    id          string                     // unexported plumbing
    createdTime *AirtableTime              //
    client      *Client                    //
    snapshot    map[string]json.RawMessage // dirty-tracking baseline
}
func (m *PrimaryModel) ID() string { return m.id }                 // accessor (RECORD_ID() target, §2.2.8)
func (m *PrimaryModel) CreatedTime() *AirtableTime { return m.createdTime }
```

- Writable fields are **pointers** (distinguish absent vs cleared for PATCH); slices for
  list/multi-select. `json:"fld…"` tags carry **field IDs**.
- Computed vs writable is identical at the type level (Go has no read-only fields); the
  read-only contract is enforced **only by payload builders** (`toCreateFields`/`dirtyFields`
  emit writable field IDs). Covered by offline tests.
- Decode via `encoding/json` into the struct; **create/update payloads hand-rolled**
  (writable-only `map[string]json.RawMessage`) — the struct's `MarshalJSON` is NOT used for
  payloads (parity with all languages). Dirty tracking via unexported `snapshot` + diff.
- `int64` for auto-number/count; **`float64` for every Airtable `number`** (tests use `42.0`).

#### 2.2.1b Creation idiom: struct literal + pointer helpers

Go has no builders/named args. Runtime ships pointer-helper constructors (AWS-SDK `aws.String`
pattern): `func String(string) *string`, `Float64`, `Int64`, `Bool`, `Time(time.Time)
*AirtableTime`, `Duration(time.Duration) *AirtableDuration`. THE creation idiom in tests:
`PrimaryModel{ PrimaryKey: airtable.String("Go CRUD PKOnly 123") }`. No separate `Create…` type.

#### 2.2.2 Filter DSL: PascalCase `Eq`/`Neq`

Method names are PascalCase (Go): `Eq`, `Neq`, `Contains`, `StartsWith`, `EndsWith`,
`GreaterThan`, `LessThan`, `IsEmpty`, `IsNotEmpty`, … — same semantics, Go casing. Accessor is
a package-level value: `var PrimaryF = primaryFilters{…}`; usage `PrimaryF.PrimaryKey.Eq("x")`.
`formula_test.go` asserts PascalCase specifically (HIGH-7).

#### 2.2.3 Type-erased value = native `any`; coercions are bare package funcs

The runtime operates on `any` (decoded JSON values), the **TS/Python native-value model** —
NOT Java/Kotlin's boxed `JsonNode`. Coercion + ~80 formula functions are **package-level
funcs in `package airtable`, called bare** (same package): `V`, `N`, `S`, `A`, `AN`, `AS`,
`D`, `IsTruthy`, `LOWER`, … `V(value any) any` boxes a Go value (dereferencing pointers,
nil→nil) into the `any` representation used by `toCreateFields`. Field refs emit
`V(m.FieldName)`; literals emit bare native Go literals (string→`"x"`, number→`5.0`,
bool→`true`, null→`nil`) — exactly like TS/Python (§3.4).

#### 2.2.4 Generic sum types via first-token peek (the F1.12 gate)

`encoding/json` analog of Jackson's peek: custom `UnmarshalJSON` (pointer receiver) inspects
raw bytes, then unmarshals the payload into the captured type parameter.

- `VecOrValue[T]`: first non-space byte `[` → `Multiple([]T)`; else `Single(T)`.
- `MaybeSpecialOrError[T]`: object with `"specialValue"` → `Special`; `"error"` → `Error`;
  else `Value(T)`.
- **Nested `VecOrValue[MaybeSpecialOrError[T]]`:** inside the outer `UnmarshalJSON`,
  `var elem T; json.Unmarshal(elemBytes, &elem)` — at runtime `&elem` is the _concrete_
  `*MaybeSpecialOrError[string]`, whose pointer-receiver `UnmarshalJSON` `encoding/json`
  finds **via reflection on the runtime type** (independent of the generic constraint). This
  is the single biggest Go risk; **F1.12 must prove it by running**, not by inference: decode
  AND encode round-trips for `MaybeSpecialOrError[string]`, `[float64]`, `[AirtableTime]`,
  `VecOrValue[string]`, and nested `VecOrValue[MaybeSpecialOrError[string]]` on a real struct
  field — confirming the nested element actually routed through the custom unmarshaler.
- DX accessors: `func (m MaybeSpecialOrError[T]) Value() (T, bool)`;
  `func (v VecOrValue[T]) Values() []T`; `CleanValues()` for the nested case.

#### 2.2.5 Flat single package; one directory

Go forbids `package != directory`, so Java's multi-subdir-flat-package trick is impossible.
**All generated + static files live in ONE directory** under **`package airtable`** (short,
lowercase, idiomatic; flagged minor — could be `myairtable`). No import cycles (same package).
Files split by concern (`model_primary.go`, `options_primary.go`, …, `airtable.go`, + static
files). Integration tests import this package from a **sibling** directory. `reset_folder`
wipes & repopulates `output/` each run; tests outside `output/` untouched.

#### 2.2.5b Static-runtime unit tests live in-place (CRIT-3 fix)

No symlink module. The static runtime IS its own testable module: `static/go/go.mod`
(`module myairtable/airtable`, package `airtable`) + unit tests as `static/go/*_test.go`
beside the code. `copy_static_files` **excludes `go.mod` and `*_test.go`** from the copy into
`output/`. `checks.sh` runs `(cd static/go && go test ./...)`. This sidesteps all symlink /
module-boundary fragility and keeps the runtime self-testing.

#### 2.2.6 Errors: typed + sentinels, returned

```go
var ( ErrNotFound = errors.New("airtable: record not found")
      ErrMissingCredentials = errors.New("airtable: missing credentials") )
type APIError struct { StatusCode int; Type, Message string }   // errors.As
type RateLimitError struct { RetryAfter time.Duration }         // errors.As (client retries internally)
type HTTPError struct { StatusCode int; Body string }
type DecodingError struct { Err error }                         // Unwrap → errors.As/Is
```

All I/O returns `(T, error)`. Wire error body (`{"error":{"type","message"}}` or string) is
decoded by an unexported `errorEnvelope` struct in `errors.go` → `APIError`. `errors.Is(err,
ErrNotFound)` / `errors.As(err, &apiErr)`.

#### 2.2.6b Date / Duration / numbers

- **Date:** `type AirtableTime struct{ time.Time }`; `UnmarshalJSON` tries RFC3339-fractional
  → RFC3339 → date-only `2006-01-02`→midnight UTC; `MarshalJSON` emits RFC3339. Models use
  `*AirtableTime` (plain `time.Time` can't parse date-only). `omitempty` works on the pointer.
- **Duration:** `type AirtableDuration time.Duration`; wire = **numeric seconds** (locked by
  Swift/Kotlin/Java live verification). Custom (un)marshaler (default would be int64 nanos).
- **`EXP(1.0)` ULP:** Go's `math.Exp(1.0)` may differ from V8's `Math.E`; **verify-first**,
  pin `EXP(1.0)` to `math.E` if the live round-trip mismatches (runtime parity test).

#### 2.2.7 Select options: typed-string constants

`type PrimarySingleSelectOption string` + `const PrimarySingleSelectOptionFoo … = "Foo"`.
Marshals as a plain string (underlying type IS string) — no custom marshaler. Const names
PascalCase, type-prefixed for uniqueness; collisions deduped with numeric suffix (parity with
`_choice_to_entry`).

#### 2.2.8 Table layer: generics + per-model fluent methods + `ID()` accessor

- Static `Table[T any, PT interface{ *T; Model }]` (pointer-constraint idiom so `new(T)`+
  decode works and pointer-receiver `Model` methods are visible):
  ```go
  type Model interface { TableID() string; toCreateFields() map[string]json.RawMessage; setID(string); setClient(*Client); … }
  func (t Table[T,PT]) Get(ctx context.Context, id string) (PT, error) { var v T; … json.Unmarshal(…, &v); PT(&v).setClient(t.client); return &v, nil }
  ```
  (Exact constraint shape is an F1.12 gate.) Generated `Airtable` exposes `Primary
Table[PrimaryModel, *PrimaryModel]` etc. Includes `Upsert` (Rust/Java parity). `DictTable`
  mirrors the API for raw `Fields`.
- Go methods can't add type params → **per-model fluent CRUD is generator-emitted**:
  `func (m *PrimaryModel) Save(ctx context.Context) error { return modelSave(ctx, m) }`
  (likewise `Fetch`, `Delete`), delegating to generic free funcs in `model.go`. Model holds
  attached `client` + table id; `requireID()`/`requireClient()` **return errors** when unset
  (no panic — locked constraint).
- **`ID()` accessor** (HIGH-6): `id` stays an unexported field, but each model exposes
  `func (m *PrimaryModel) ID() string`. The transpiler's `RECORD_ID()` emits `V(m.ID())`.
  Resolves the unexported-field-vs-transpiler-access tension.

#### 2.2.9 URL encoding verify-first

`net/url`: `url.Values.Encode()` does space→`+`, `+`→`%2B` (query). Like Java's `URLEncoder`,
**likely** correct for `filterByFormula=LEN({f})+1` — but an inference; the **verify-first
spike** confirms a live round-trip. **Path segments** (table names w/ spaces) use
`url.PathEscape` (→`%20`), never query encoding. Pinned by `client_url_encoding_test.go`.

#### 2.2.10 Formatting & lint

- **`gofmt`-clean by construction:** generated output emitted already-formatted; verified via
  `gofmt -l output/` (must print nothing) — free and stronger than Java. Unused imports are a
  **compile error**, so the writer's import accumulator must be **exact AND alphabetically
  sorted** (gofmt reorders imports; R16). All imports are stdlib (single group).
- **`go vet`** always; **`golangci-lint`** behind a `command -v` warn-skip guard. Generated
  code is never linted (initialism `Id`→`ID` noise on arbitrary Airtable field names);
  hand-written `static/go` follows Go casing.

### 2.3 Other settled choices

| Decision            | Value                                                                                        |
| ------------------- | -------------------------------------------------------------------------------------------- |
| Go version          | floor **1.21** (`slices`/`maps` stdlib; generics since 1.18); **1.23 recommended** in go.mod |
| Test framework      | stdlib **`testing`** (`t.Run`, `t.Fatalf`) — no testify                                      |
| Integration phasing | ordered `t.Run` subtests within a file; package setup in `TestMain`                          |
| Test parallelism    | NO `t.Parallel()` across CRUD files; distinct primary keys per file                          |
| File naming         | `snake_case.go`; exported identifiers PascalCase via `name_pascal()`                         |
| Linked records      | raw `[]string` IDs; resolve via `airtable.Secondary.Get(ctx, id)`                            |
| Doc comments        | `// …` line comments (no block-doc HTML hazard — `_javadoc_escape` dropped)                  |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/go.py                  # NEW ~900 LOC (mirrors java.py; fewer files: no enums/
                                      #   getters/setters/annotations; struct tags inline)
src/utils/write_to_go_file.py         # NEW WriteToGoFile: package decl; SORTED+EXACT import
                                      #   accumulator (unused/unsorted = fail); // doc comments;
                                      #   struct open/close; struct-FIELD-WITH-JSON-TAG emitter;
                                      #   interface emitter; typed-string-const emitter;
                                      #   _go_ident() (_-suffix; keywords+predeclared);
                                      #   _go_string_literal(); _choice_to_const()
src/utils/type_mapper.py              # MOD: GENERIC_TO_GO; "go" in Language Literal (:341);
                                      #   LANGUAGE_CONFIGS "go" (list_fmt="[]{0}",
                                      #   union_fmt="VecOrValue[{0}]", unknown="any"; NO
                                      #   computed_union_fmt — uses apply-fn path like Kotlin/Java);
                                      #   map_go_type(); apply_go_computed_wrapping();
                                      #   is_already_list "go" (startswith "[]"); map_types()
                                      #   first-pass go lines (:~221/:~228); apply_disambiguated_type
                                      #   go line (:884) → field._go_type = apply_go_computed_wrapping(
                                      #   render_type(field,"go",is_list=is_list), field)
src/utils/write_to_file.py            # MOD: "go" in language Literal (:49); add "go" to the
                                      #   //-comment header case (:74)
src/meta.py                           # MOD: _go_type PrivateAttr (after :383); go_type property (:~610)
src/formulas/formula_transpiler.py    # MOD: "go" in Language Literal (:21); _self (:323) → add "go"
                                      #   to the (python,rust,swift) bucket BUT with receiver "m"
                                      #   (Go field access m.Field); _runtime (:326) bare (§3.4);
                                      #   Go arms per §3.4 (smaller than Java's — Go mostly reuses
                                      #   the TS/Python native-value path)
main.py                               # MOD: import generate_go (:11); `go` command (:~230);
                                      #   all() go_folder option (:~371) + if go_folder block (:~436)
checks.sh                             # MOD: Go section (command -v go guard; cd static/go && go test;
                                      #   go vet; gofmt -l guard; golangci-lint command -v guard)
static/go/                            # NEW static runtime + go.mod + *_test.go (§2.2.5b, §4)
tests/test_generators.py             # MOD: TestGo* classes; PRIMARY make_test_base dict (:86) gains
                                      #   "_go_type": None; SECOND dict (:469) gains "_go_type",
                                      #   "_rust_type", "_swift_type", "_java_type" (3 pre-existing
                                      #   gaps + go)
tests/test_formula_transpiler_go.py   # NEW (~45 cases; mirror Java/Kotlin/Swift twins)
```

Static unit tests live in `static/go/*_test.go` (§2.2.5b), NOT a separate `tests/go_static/`:

```
static/go/
├── go.mod                            # module myairtable/airtable (EXCLUDED from copy)
├── <runtime *.go>                    # §4
└── *_test.go                         # EXCLUDED from copy — Java/Kotlin parity inventory:
    ├── pojo_model_test.go            # F1.12 prototype gate (§2.2.1/2.2.4/2.2.5/2.2.6b/2.2.8)
    ├── harness_test.go, query_build_test.go, exception_decoding_test.go,
    ├── cache_store_test.go, client_cache_policy_test.go, client_hardening_test.go,
    ├── client_url_encoding_test.go, date_decoding_test.go, dx_helpers_test.go,
    ├── special_error_decoding_test.go, fields_dual_access_test.go, value_coercion_test.go,
    ├── table_bounded_ops_test.go
    ├── formula_test.go               # test_formula.rs parity (§5 F7.4)
    └── airtable_runtime_test.go      # ~167 cases (test_airtable_runtime.rs parity)
```

### 3.2 Generated output (per run)

```
go/output/                            # ONE directory, package airtable; generator emits NO go.mod
├── airtable.go                       # Airtable struct: BASE_ID, Client, per-table fields, ctors
├── model_{table}.go                  # struct + json tags + ID()/CreatedTime() + Save/Fetch/Delete + evaluate*
├── options_{table}.go                # typed-string-const groups
├── fields_{table}.go                 # field ID/name consts, id↔name maps, allIds, View consts
├── filters_{table}.go                # formula builders + package var {Table}F
└── <static files copied from static/go/ (excluding go.mod, *_test.go)>
```

### 3.3 Test repo (`myairtable-tests`)

```
go/
├── go.mod                            # HAND-WRITTEN: module myairtabletests ; go 1.23 ; NO requires
├── output/                           # regenerated by build.sh — package airtable (imported as
│                                      #   "myairtabletests/output")
└── tests/                            # package tests ; import "myairtabletests/output"
    ├── main_test.go                  # TestMain: .env walker (up to .git) + Airtable factory + primaryKey(suite,label)
    ├── harness_test.go               # smoke: VERSION reachable
    ├── struct_crud_via_table_test.go, orm_crud_via_table_test.go, orm_crud_via_model_test.go,
    ├── serializing_test.go, filter_by_formula_test.go, runtime_formulas_test.go,
    ├── caching_test.go, linked_records_test.go, complex_properties_test.go,
    └── special_error_deser_test.go
build.sh                              # MOD: --go-folder "$AIRTABLE_DIR/go/output"
test.sh                               # MOD: go case (go test -run …) + add `go` to all loop + exec path
checks.sh                             # MOD: Go block (command -v go; cd go && go build ./...; go vet;
                                      #   gofmt -l; golangci-lint command -v guard)
```

`test.sh` go case (mirrors Java; Go `-run` regex on test func names):

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

`.env` keys consumed: `AIRTABLE_BASE_ID`, `AIRTABLE_API_KEY` (same as all languages).

## 3.4 Transpiler integration (Go-specific arms)

**Key correction from v1:** Go's runtime value is **native `any`** (TS/Python model), so Go
reuses the **default (TS/Python) emit path** for most sites, NOT the boxed Java/Kotlin arms.
Wiring:

- **`_self` (:323):** add `"go"` → receiver `"m"` (generated `evaluate*` methods use
  `func (m *{Table}Model)`, so `m.FieldName` is valid). Field-ref emits `V(m.FieldName)`.
- **`_runtime` (:326) + call sites:** Go uses **bare same-package calls**. Implement via a
  `_rt(name)` helper returning `name` for Go and `f"{self._runtime}.{name}"` otherwise (or
  add `self._runtime_sep`), applied at `_emit_function_call` (:473/:476), `_emit_str` tail
  (:1148 — Go joins Kotlin's bare-`S()` arm), `_emit_num` tail (:1174 — bare `N()`). Forbid
  `_runtime=""` as a bare-concat magic value; use the helper.
- **Literals:** Go emits **bare native literals** (string `"x"`, number `5.0`, bool `true`,
  null `nil`) — same as the TS/Python default arms; NOT `JsonPrimitive`/`V(...)` boxing.
- **AND/OR/NOT/XOR:** inline Go `IsTruthy(a) && IsTruthy(b)` / `||` / `!IsTruthy(a)` /
  `IsTruthy(l) != IsTruthy(r)` (bool → `any`).
- **NO TERNARY (Go-unique):** `IF`/`IFS`/`SWITCH` **cannot** emit `cond ? a : b`. They emit
  **runtime function calls**: `IF(cond, t, f any) any`, `IFS(pairs ...any) any`,
  `SWITCH(expr any, fallback any, pairs ...any) any` (alternating pattern/value varargs,
  Java's flat-varargs shape). These funcs live in `runtime.go` (§4).
- **RECORD_ID:** `V(m.ID())` (§2.2.8). **TRUE/FALSE/BLANK:** `V(true)`/`V(false)`/`nil`
  (or `BLANK()` helper). **COUNTALL:** `V(float64(len(A(args...))))` with `A(vals ...any)
[]any`. **LEN/INT/ABS/SQRT/EXP/POWER/MOD/MIN/MAX/SUM/ROUND/CONCATENATE/REPT/regex\*/
  date-part/DATESTR/TIMESTR/str-methods/encode-url:** route through `runtime.go` funcs (these
  are the existing `return None` fall-throughs — just add `"go"` to each guard tuple).
- **`_emit_binary_op`/`_emit_unary_op`:** arithmetic/comparison/`&`-concat emit Go-native
  forms over `N(...)`/`S(...)` (mirror the TS default arm with Go operators); `=`/`!=` use
  the runtime equality coercion (`IsEqual(l, r)` helper) rather than `==` on `any`.

Net Go-specific _distinct_ arms: ~12–15 (bare-qualifier sites, no-ternary IF/IFS/SWITCH,
RECORD_ID/COUNTALL, equality). The remaining ~25 sites are covered by adding `"go"` to
existing `return None` fall-through tuples or by the shared default path.
`test_formula_transpiler_go.py` pins every category.

## 4. Static Runtime Contract (`static/go/`, ~25 files + go.mod, ~4,000 LOC)

| File                            | Contents                                                                                                                                                    |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `errors.go`                     | sentinels + typed errors (`APIError`,`RateLimitError`,`HTTPError`,`DecodingError`) + unexported `errorEnvelope` wire decoder (§2.2.6)                       |
| `client.go`                     | `Client`, `*http.Client`, bearer auth, ctx-aware 429 retry/backoff, all record endpoints, owns cache, chunk-of-10 batching; path-vs-query encoding (§2.2.9) |
| `cache.go`                      | TTL cache behind `sync.RWMutex`; per-table wipe; `InvalidateAll()`                                                                                          |
| `json.go`                       | shared (un)marshal helpers; `V()` boxing (pointer-deref); `AirtableTime`/`AirtableDuration` (un)marshalers (§2.2.6b)                                        |
| `model.go`                      | `Model` interface + generic `modelSave/modelFetch/modelDelete` backing emitted fluent methods (§2.2.8)                                                      |
| `record.go`                     | generic `Record[T]` envelope (id, createdTime, fields)                                                                                                      |
| `fields.go`                     | `Fields` wraps `map[string]json.RawMessage`; dual ID/name `Get`/`Set` (ID-first, name fallback)                                                             |
| `dict_table.go`                 | raw CRUD returning `Fields`; mirrors `Table` API                                                                                                            |
| `table.go`                      | generic `Table[T,PT]` — typed CRUD + `Upsert`, batching, cache invalidation (§2.2.8)                                                                        |
| `query.go`                      | `Query`: filter/sort/fields/maxRecords/pageSize/view/returnFieldsByFieldID; `toParams()`; `WithView`                                                        |
| `view.go`                       | `type View interface{ ViewID() string }`                                                                                                                    |
| `sort.go`                       | `Sort` spec + `SortDirection` consts                                                                                                                        |
| `helpers.go`                    | pointer helpers `String/Float64/Int64/Bool/Time/Duration` (§2.2.1b)                                                                                         |
| `vec_or_value.go`               | `VecOrValue[T]` + (un)marshaler + `Values()` (§2.2.4)                                                                                                       |
| `maybe_special_or_error.go`     | `MaybeSpecialOrError[T]` + (un)marshaler + `Value()`; `SpecialNumber`, `ErrorValue` (§2.2.4)                                                                |
| `formula.go`                    | `Formula` + combinators (And/Or/Not/Xor) + base field helpers                                                                                               |
| `formula_fields.go`             | per-type formula builders (Text/Number/Date/Boolean/Select/MultiSelect/Lookup/ID/Attachment), Eq/Neq                                                        |
| `formula_date.go`               | date-formula sub-DSL (operand/literal/comparison)                                                                                                           |
| `runtime.go`                    | ~80 formula funcs + coercions `V/N/S/A/AN/AS/D/IsTruthy` + `IF/IFS/SWITCH/IsEqual` (no-ternary, §3.4) + EXP pin                                             |
| `attachment.go`                 | `Attachment` + inlined `Thumbnails`/`Thumbnail`                                                                                                             |
| `collaborator.go` / `button.go` | data carriers                                                                                                                                               |
| `runtime_info.go`               | `VERSION` constant                                                                                                                                          |

(Collapses vs Java: no `AirtableJson`/`AirtableJacksonModule`/`AirtableDateParser` trio
(custom marshalers live with types); no separate Serializer/Deserializer files; no
`ModelOps`/`AirtableModel` split; error envelope inlined in `errors.go`; Thumbnails inlined.)

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"go"` in `write_to_file.py` Literal (:49) + `//` header case (:74).
- 1.2 `write_to_go_file.py` (`WriteToGoFile` + **sorted+exact import accumulator** + `_go_ident`
  keyword/predeclared set + `_go_string_literal` + `_choice_to_const` + struct-field-with-tag).
- 1.3 Type wiring — ALL: `GENERIC_TO_GO`; `"go"` in type_mapper Literal; `LANGUAGE_CONFIGS`
  entry (`[]{0}`, `VecOrValue[{0}]`, `unknown="any"`, **no `computed_union_fmt`**);
  `map_go_type()`; `apply_go_computed_wrapping()`; `is_already_list` go; `map_types()`
  first-pass go lines; `apply_disambiguated_type()` go line (:884); meta.py `_go_type` +
  property; **PRIMARY** `make_test_base` dict gains `"_go_type"`, **SECOND** dict gains
  `"_go_type"` + the pre-existing-missing `"_rust_type"`/`"_swift_type"`/`"_java_type"`.
- 1.4 `main.py go` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--go-folder`).
- 1.6 `static/go/go.mod` (module `myairtable/airtable`, go 1.23) + copy-exclusion of
  `go.mod`/`*_test.go` (§2.2.5b).
- 1.7 `myairtable-tests/go/` skeleton: hand-written `go.mod` (`module myairtabletests`),
  `output/` package dir, `tests/` package importing `myairtabletests/output`.
- 1.8 `myairtable-tests/build.sh`: `--go-folder`.
- 1.9 `myairtable-tests/test.sh`: go case (§3.3) + `go` in all loop + exec path.
- 1.10 `myairtable-tests/checks.sh`: Go block (build + vet + gofmt -l + golangci-lint guard).
- 1.11 `myairtable/checks.sh`: Go section (`command -v go` guard; `cd static/go && go test`;
  vet; gofmt -l; golangci-lint guard).
- 1.12 **Prototype gate** `static/go/pojo_model_test.go` proving ALL risky foundations before
  templating: (a) struct decode of `json:"fld…"` field-ID keys incl. computed pointer fields;
  (b) generic sum-type round-trips incl. the **nested `VecOrValue[MaybeSpecialOrError[T]]`
  pointer-receiver dispatch proven by running** (§2.2.4) — decode AND encode; (c)
  `AirtableDuration` encodes as numeric seconds; (d) `AirtableTime` 3-format decode; (e)
  snapshot + writable-only payload builder; (f) the `Table[T,PT]` pointer-constraint idiom
  compiles and `Get` decodes into `new(T)` and sets the client.

**Exit:** `uv run main.py go <folder>` exits 0 (stub ok); `go build ./...` compiles both
modules; prototype green; both checks.sh/test.sh run their go sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `errors.go`. 2.2 value/sum types + `AirtableTime`/`AirtableDuration` (`json.go`),
  `record.go`, `attachment.go`, `collaborator.go`, `button.go`, `sort.go`, `view.go`.
- 2.3 `client.go` — starts with the URL-encoding spike (§2.2.9).
- 2.4 `query.go` incl. `WithView`; 2.5 `fields.go`; 2.6 `dict_table.go`; 2.7 `cache.go`
  skeleton (API + mutex; TTL/LRU → F9). 2.8 `runtime.go` coercions + `helpers.go` ptr ctors.
- 2.9 Unit tests: query_build, exception_decoding (errors.As/Is), fields_dual_access,
  date_decoding, special_error_decoding, value_coercion, client_url_encoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration ASAP

- 3.1 `generate_go()` + static copy (exclude runtime/formula files per flags; exclude
  `go.mod`/`*_test.go`). 3.2 `write_options()`. 3.3 `write_field_types()` (consts + maps +
  View consts). 3.4 `write_tables()` (dict accessor) + 3.5 `write_main()` (`Airtable` struct +
  `New`/`NewWithKey`/`…cacheSeconds`). 3.6 Offline `TestGo*` content tests.
- 3.7 **Integration**: `struct_crud_via_table_test.go` green vs real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `model.go` + generic ops; 4.2 `table.go` `Table[T,PT]` incl. `Upsert`.
- 4.3 `write_models()` — struct + json-tag pointer fields + `ID()`/`CreatedTime()` + snapshot
  - `Save/Fetch/Delete` + doc comments + `evaluate*` (runtime flag). 4.4 ORM accessor.
- 4.5 `TestGoComputedFields` (computed excluded from payload; writable included; wrappers/tags
  present; evaluate gated). 4.6 Offline `serializing_test.go` (8 cases).
- 4.7 **Integration**: orm_crud_via_table (pk-only, all-simple, upsert insert/update,
  111-record batch, field selection, maxRecords, invalid-ID error), orm_crud_via_model.

### Feature 5 — Complex Field Types [P2]

- 5.1 attachment upload (URL); 5.2 collaborator; 5.3 computed `MaybeSpecialOrError` e2e;
  5.4 button; 5.5 duration round-trip magnitude. 5.6 **Integration** complex_properties_test.go.
  5.7 **Integration** special_error_deser_test.go.

### Feature 6 — Linked Records [P2]

- 6.1 raw `[]string` fields. 6.2 **Integration** linked_records_test.go (resolve via `Secondary.Get`).

### Feature 7 — Formula Builders [P2]

- 7.1 formula field types (Eq/Neq); 7.2 combinators; 7.3 `write_formula_helpers()` →
  `filters_{table}.go` + `var {Table}F`.
- 7.4 `formula_test.go` — **exact parity with `tests/test_formula.rs`** category-by-category
  (combinators, id, text, single/multi-select, number, boolean, date, attachment, lookup);
  match Rust counts within ±5% (do a literal diff vs test_formula.rs in F11).
- 7.5 **Integration** filter_by_formula_test.go.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler wiring per §3.4 (`_self="m"`, bare `_rt` helper, native literals, no-ternary
  IF/IFS/SWITCH, RECORD_ID/COUNTALL/equality, `"go"` in fall-through tuples). Evaluate
  methods return `any`. 8.2–8.8 `runtime.go` groups: math (EXP pin), logic (IF/IFS/SWITCH),
  string, date (time pkg), array, regex, coercions. 8.9 wire `evaluate*` on models.
- 8.10 `tests/test_formula_transpiler_go.py` (~45). 8.11 `airtable_runtime_test.go` ~167.
- 8.12 **Integration** runtime_formulas_test.go.

### Feature 9 — Caching [P3]

- 9.1 TTL/LRU/per-table wipe; 9.2 cached reads; 9.3 mutation invalidation; 9.4
  `InvalidateAllCaches()` + per-table. 9.5 **Integration** caching_test.go (~10, Rust parity).

### Feature 10 — Serialization (integration) [P3]

- 10.1 network-bound serializing cases (linked-record arrays, createdTime round-trip, unsaved-id).

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 file-by-file test diff vs Java/Kotlin/Swift/Rust/Python/TS (literal compare formula +
  runtime case lists); close gaps. 11.2 `./checks.sh` both repos green; 11.3 `./test.sh all`
  green (eight languages); 11.4 `main.py all` with go; 11.5 README updates (both repos: Go
  version, `go build` step, go.mod not emitted).

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

| #   | Risk                                                       | Mitigation                                                                        |
| --- | ---------------------------------------------------------- | --------------------------------------------------------------------------------- |
| R1  | Generics + `encoding/json` nested sum-type decode          | §2.2.4 first-token peek; F1.12(b) **runtime** proof of nested pointer-dispatch    |
| R2  | `Table[T,PT]` pointer-constraint won't compile/decode      | F1.12(f) compile + `Get` decode + client-set proof                                |
| R3  | Go forbids package≠dir                                     | §2.2.5 single flat dir/package; tests in sibling package                          |
| R4  | Unused/unsorted imports break build / gofmt                | §2.2.10 exact **sorted** import accumulator; `go build` + `gofmt -l` in CI        |
| R5  | Duration default JSON = nanoseconds                        | `AirtableDuration` marshaler; F1.12(c) numeric-seconds assert                     |
| R6  | `time.Time` can't parse date-only                          | `AirtableTime` 3-format; date_decoding_test                                       |
| R7  | URL encoding (`+`, spaces, path vs query)                  | §2.2.9 verify-first spike; client_url_encoding_test; live round-trip              |
| R8  | `math.Exp(1.0)` mismatch vs Airtable                       | verify-first; pin EXP(1.0) to math.E; runtime parity test                         |
| R9  | Go keyword/predeclared collisions                          | `_go_ident()` `_`-suffix; tests incl. `string`/`error`/`any`/`nil`                |
| R10 | Transpiler emits non-Go (ternary, qualified calls, boxing) | §3.4 native-value model + no-ternary IF/IFS/SWITCH; test_formula_transpiler_go.py |
| R11 | Disambiguated lookup/rollup skip Go types                  | F1.3 explicit `map_types` + `apply_disambiguated_type` (:884) tasks + test        |
| R12 | unexported `id` blocks RECORD_ID() transpilation           | §2.2.8 `ID()` accessor; transpiler emits `V(m.ID())`                              |
| R13 | Pointer-optional ergonomics balloon test verbosity         | pointer-helper ctors (§2.2.1b); accept (idiomatic for optional JSON)              |
| R14 | `float64` equality in tests                                | numbers-are-float64 documented; tests use `42.0`                                  |
| R15 | golangci-lint initialism noise on generated names          | never lint generated; static/go follows Go casing                                 |
| R16 | gofmt reorders imports → `gofmt -l` flags generated files  | accumulator emits stdlib imports alphabetically sorted                            |
| R17 | `View` interface name collides with a table named "View"   | accept (dedup yields `ViewView`/`ViewsView`); one-line note; revisit if real      |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py go <folder>` generates a compiling Go package (`go build` clean, `gofmt -l` empty, `go vet` clean).
- [ ] `uv run main.py all --go-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Go included.
- [ ] `./test.sh all` (myairtable-tests) green with Go included (**eight languages**).
- [ ] All eleven integration test files green (struct/orm crud ×3, serializing, filter,
      runtime, caching, linked, complex, special-deser).
- [ ] Unit-test parity: `static/go/*_test.go` matching Java/Kotlin inventory; formula builder
      = test_formula.rs categories; runtime ~167 within ±5% of Rust/Java.
- [ ] Upsert + dual ID/name Fields access + DX helpers (Value/CleanValues/View/ID) tested.
- [ ] Generated code is idiomatic Go (struct tags, pointer optionals, generics,
      errors-as-values, native-`any` runtime, no ternary-isms, gofmt-clean).

```

```
