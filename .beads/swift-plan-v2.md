# Swift Language Support — Implementation Plan v2 (final, user-approved)

> **Changes from v1**: resolved three critical architecture issues up-front (Observable+Codable, cache topology, F-namespace collision); added upsert parity, dict-table field-name access, generator assertions spec; moved offline serialization tests earlier; hardened `swift-format`, `swift build`, and Swift-Testing concurrency concerns.
>
> **v2 updates applied from user answers (2026-04-16)**:
>
> 1. Swift Testing confirmed.
> 2. Module name `MyAirtable` confirmed (not configurable).
> 3. **Do NOT emit `Package.swift`** from the generator — other languages don't. The test repo keeps a hand-written `swift/Package.swift`; the generator writes source files only.
> 4. Filter accessor is `{Table}Model.f.fieldName.equals(...)` (lowercase `.f` — follows the existing `F` pattern in other languages, adapted to Swift property conventions).
> 5. Concurrency: within-file **sequential** via `@Suite(.serialized)`; between-file parallel (matches vitest). Cleanup in every test. Distinct keys across files to avoid collisions.
> 6. Confirmed: ORM models are `@Observable` **classes**; dict/raw records are **structs**.
> 7. `DictTable` dual ID/name access confirmed.

## 1. Overview & Goals

Add full-parity Swift code generation to `myairtable`, matching the coverage of existing Python, TypeScript, JavaScript, and Rust targets. Generated Swift code must feel **idiomatic** (actors, `Codable`, `@Observable`, async/await, value-type generics) — not a mechanical port of the Rust target.

**Scope:**

- Generator at `myairtable/src/generators/swift.py`
- Static runtime at `myairtable/static/swift/`
- Unit tests (parity with `tests/test_generators.py`, `tests/test_formula_*.py`, `tests/test_airtable_runtime.*`)
- Integration tests at `myairtable-tests/swift/` (parity with Rust/Python/TS)
- CLI wiring (`main.py` `swift` command + `all` integration)
- Updates to `checks.sh` (both repos), `myairtable-tests/test.sh`, `myairtable-tests/build.sh`

**Non-goals (v1):**

- SwiftUI example app
- CocoaPods / Carthage support (SPM only)
- iOS 16 / macOS 13 backport (minimum = `@Observable` requirement)

## 2. Design Decisions

### 2.1 Locked from memory (`project_swift_design_decisions.md`)

| Decision        | Value                                                                |
| --------------- | -------------------------------------------------------------------- |
| Swift version   | 6                                                                    |
| Package manager | SPM only                                                             |
| Date type       | `Date` + custom `ISO8601DateFormatter`                               |
| Duration type   | `TimeInterval` (`Double`, seconds)                                   |
| File layout     | Subdirectory pattern (Models/, Options/, Types/, Formulas/, Tables/) |
| Linked records  | `LinkedRecord<T>` + `@dynamicMemberLookup` + `KeyPath` subscripts    |
| Validation      | `Codable` only (no Zod equivalent)                                   |
| Model class     | `@Observable` class — `let` for computed, `var` for writable         |
| Error type      | `AirtableError: Error` enum with associated values                   |
| Schema          | Typed `BaseSchema` struct with literals (no JSON parse at runtime)   |

### 2.2 Newly locked (resolving critic issues)

#### 2.2.1 @Observable + Codable co-existence (CRIT-1)

`@Observable` macro breaks memberwise `Codable` synthesis. **Resolution**: generator emits **manual** `CodingKeys` enum + manual `init(from decoder:)` + manual `encode(to:)` for every model. A hand-written prototype is produced and tested in **Phase 0** (Feature 1 exit), not later. This is validated by a golden-file compile test before generator templating begins.

#### 2.2.2 Dirty tracking (MED-1)

`@Observable` observation is for **SwiftUI binding**, not for partial-update payloads. Dirty tracking uses an **explicit snapshot dict** (`[String: AnyEncodable]`) stored in a private `_snapshot` property, captured after decode / create / save. `dirtyFields()` computes a diff — mirrors Rust's `to_save_json`. Snapshot is excluded from `Codable`.

#### 2.2.3 Concurrency & cache topology (CRIT-2)

The cache is **NOT** owned by table wrappers. Instead:

- `AirtableClient` actor owns a single `CacheStore` actor (keyed by `tableId` + `cacheKey`).
- `OrmTable<T, C>` and `DictTable` are `Sendable` struct front-ends that forward to the client actor for all I/O and cache interaction.
- Tables expose `.invalidateCache()`; the client's `invalidateAllCaches()` cascades.
- This preserves `Sendable` structs while satisfying Swift 6 strict-concurrency.

#### 2.2.4 `F` namespace disambiguation (7) — user-approved

Two different namespaces in v1 both called `F`. **Resolution**:

- **Filter builders**: exposed on model as a static property `{Table}Model.f` returning `{Table}Filters` struct. Call site: `PrimaryModel.f.primaryKey.equals("foo")`. This follows the `.F` / `::F` pattern in the other languages (Swift lowercase conventions → `.f`).
- **Runtime**: static methods on enum `AirtableRuntime` (e.g., `AirtableRuntime.sum(a, b)`). The formula transpiler emits calls to `AirtableRuntime.*` — kept distinct from `.f` to avoid confusion in model bodies that reference both.

#### 2.2.5 `DictTable` field-name + field-ID dual access (HIGH-2)

`{Table}Fields` enum emits both `.primaryKeyId` and `.primaryKeyName` static string constants. `DictTable.Fields` value wraps `[String: Any]` with `get/set(_ key: String)` that accepts **either** the ID or name (ID-first lookup fallback to name). Matches Rust `Fields.get()` semantics and unlocks serialization tests at parity.

#### 2.2.6 `Sendable` conformance (LOW-1)

All public static types declare `Sendable` where applicable: `AirtableQuery`, `AirtableError`, `AirtableAttachment`, `AirtableCollaborator`, `AirtableButton`, `AirtableRecord<T>`, `RecordId`, `SortDirection`.

#### 2.2.7 Swift Testing concurrency (MED-3) — matches TS/JS pattern

- Within-file: **sequential** via `@Suite(.serialized)` on every integration file. Mirrors vitest's default within-file sequential execution (see `myairtable-tests/typescript/tests/model-crud-via-table.test.ts` for the reference pattern of chained `describe` blocks sharing an `id` variable).
- Between-file: **parallel** (Swift Testing default; matches vitest behavior). Each file uses distinct primary-key values to avoid cross-file collision.
- Every test cleans up records it created (matches TS/JS delete-at-end convention).
- Integration test files are `@Suite("name", .serialized) struct FooTests { … }`.
- No `TestFixture` actor needed — tests share a module-level `let airtable = Airtable()` constructed once per test-run.

### 2.3 Other settled design choices

| Decision             | Value                                                                  | Rationale                                    |
| -------------------- | ---------------------------------------------------------------------- | -------------------------------------------- |
| Test framework       | Swift Testing (`@Test`, `#expect`)                                     | Swift 6 native; concise                      |
| Formatter            | `swift-format` pinned to Swift 6.0 toolchain                           | Apple official; version check in `checks.sh` |
| Platform min         | iOS 17 / macOS 14 / watchOS 10 / tvOS 17 / visionOS 1                  | `@Observable` requirement                    |
| Module name          | `MyAirtable` (constant)                                                | Simple, predictable                          |
| External deps        | None (Foundation only)                                                 | Zero-dep runtime                             |
| File naming          | `PascalCase.swift`                                                     | Swift convention                             |
| Property naming      | `lowerCamelCase` via `name_camel()`                                    | Swift convention                             |
| Reserved-word escape | Backtick-quote (`` `class` ``)                                         | Swift convention                             |
| Codable strategy     | Manual `CodingKeys` + `init/encode` in models; field IDs as raw values | ID stability; required by @Observable        |
| Package.swift        | **Not emitted by generator** — matches other-language behavior         | User-approved #5                             |
| ORM model shape      | `@Observable` **class**                                                | User-approved #9                             |
| Dict model shape     | `struct` (no `@Observable`)                                            | User-approved #9                             |
| Filter accessor      | `{Table}Model.f.fieldName`                                             | User-approved #7                             |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/swift.py               # NEW ~1000 LOC
src/utils/type_mapper.py              # MOD: add GENERIC_TO_SWIFT + LanguageConfig
src/utils/write_to_file.py            # MOD: add "swift" literal
src/utils/write_to_swift_file.py      # NEW (dedicated helper class — NOT optional)
src/formulas/formula_transpiler.py    # MOD: add Swift to CodeEmitter
main.py                               # MOD: `swift` command + `all` integration
checks.sh                             # MOD: swift-format version check + build + test
static/swift/                         # NEW static runtime (details in §4.2)
tests/test_generators.py              # MOD: add TestSwift* (specified §5.4)
tests/test_formula_transpiler_swift.py # NEW
tests/test_airtable_runtime_swift.py  # NEW (shells to swift test — PATH documented)
tests/swift_static/                   # NEW Swift package for running static-runtime XCTests
  ├── Package.swift
  └── Tests/MyAirtableStaticTests/
      ├── TestAirtableQueryBuild.swift
      ├── TestAirtableErrorDecoding.swift
      ├── TestCodableObservableModel.swift   # the @Observable/Codable prototype
      └── TestDirtyTracking.swift
```

### 3.2 Generated output (per run)

```
swift/output/                     # NOTE: generator does NOT emit Package.swift
├── Dynamic/
│   ├── Models/{Table}Model.swift
│   ├── Options/{Table}Options.swift
│   ├── Types/{Table}Fields.swift
│   ├── Formulas/{Table}Filters.swift
│   └── Tables/{Table}Table.swift
├── Static/                        # copied from static/swift/
│   ├── AirtableClient.swift
│   ├── AirtableError.swift
│   ├── AirtableModel.swift
│   ├── AirtableQuery.swift
│   ├── AirtableRuntime.swift      # formula runtime
│   ├── CacheStore.swift
│   ├── DictTable.swift
│   ├── Fields.swift
│   ├── LinkedRecord.swift
│   ├── OrmTable.swift
│   └── Types.swift
└── Airtable.swift
```

### 3.3 Test repo (`myairtable-tests`)

```
swift/
├── Package.swift                     # HAND-WRITTEN (checked into repo; not regenerated)
├── Sources/MyAirtable/               # regenerated per build (by build.sh)
└── Tests/MyAirtableTests/
    ├── TestSetup.swift                # dotenv + Airtable instance helpers
    ├── TestStructCrudViaTable.swift   # dict CRUD (parity: test_struct_crud_via_table.rs)
    ├── TestOrmCrudViaTable.swift      # parity: test_orm_crud_via_table.rs
    ├── TestOrmCrudViaModel.swift      # parity: test_orm_crud_via_model.rs
    ├── TestSerializing.swift          # parity: test_serializing.rs (unit + integration)
    ├── TestFilterByFormula.swift      # parity: test_filter_by_formula.rs
    ├── TestRuntimeFormulas.swift      # parity: test_runtime_formulas.rs
    └── TestCaching.swift              # parity: test_caching.rs
build.sh                               # MOD: --swift-folder swift
test.sh                                # MOD: swift language case
checks.sh                              # MOD: swift-format + swift build
```

## 4. Static Runtime Contract (static/swift/)

### 4.1 Runtime topology diagram

```
                ┌────────────────────────────┐
                │  AirtableClient  (actor)   │
                │  - URLSession              │
                │  - bearer token            │
                │  - listRecords() / CRUD    │
                │  - CacheStore (actor)      │
                └─────┬──────────────────┬───┘
                      │                  │
          ┌───────────▼───────────┐  ┌──▼─────────────────┐
          │  OrmTable<T, C>       │  │  DictTable          │
          │  (Sendable struct)    │  │  (Sendable struct)  │
          └───────────┬───────────┘  └──┬──────────────────┘
                      │                 │
          ┌───────────▼─────────────────▼──────────────────┐
          │  Airtable (actor) — per-table accessors        │
          └────────────────────────────────────────────────┘
```

### 4.2 File-by-file spec

| File                    | Contents                                                                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AirtableError.swift`   | Error enum: `.http(statusCode,message)`, `.api(code,message)`, `.decoding(Error)`, `.invalidUrl`, `.missingCredentials`, `.rateLimited(retryAfter:)` |
| `AirtableClient.swift`  | `actor` — URLSession, bearer auth, retry w/ exponential backoff, all record endpoints, holds `CacheStore`                                            |
| `CacheStore.swift`      | `actor` — `[CacheKey: CacheEntry]`, TTL, cascade invalidation, per-table wipe                                                                        |
| `AirtableModel.swift`   | `AirtableModel` protocol (id, createdTime, toRecord, snapshot, dirtyFields, isNew); `@Observable` base-class usage pattern                           |
| `AirtableQuery.swift`   | `Sendable struct` — formula, sort, fields, maxRecords, pageSize, view; `toQueryItems()`                                                              |
| `Fields.swift`          | `Sendable struct` — dual field-ID/name dict; `get(_:)` / `set(_:_:)`                                                                                 |
| `DictTable.swift`       | `Sendable struct` — wraps client + tableId; dict CRUD                                                                                                |
| `OrmTable.swift`        | `Sendable struct` — generic `OrmTable<Model, Create>`; typed CRUD + upsert                                                                           |
| `LinkedRecord.swift`    | `@dynamicMemberLookup` + `KeyPath` subscripts — lazy async fetch                                                                                     |
| `Types.swift`           | `RecordId = String`, `AirtableAttachment`, `AirtableCollaborator`, `AirtableButton`, `AirtableRecord<T>`, `AirtableThumbnails`, `SortDirection`      |
| `AirtableRuntime.swift` | Formula runtime — all `N/S/A`, math, logic, string, date, array, regex functions                                                                     |

## 5. Detailed Beads Hierarchy

### Epic: Swift language support

### Feature 1 — Scaffolding & Infrastructure [P0]

**Purpose**: Everything compiles, `swift build` succeeds on empty package, CI wired.

- 1.1 Add `"swift"` to `WriteToFile.language` literal.
- 1.2 Create `src/utils/write_to_swift_file.py` (`WriteToSwiftFile` subclass with `// MARK:`, `///` doc comments, `struct_def`, `class_def`, `enum_def`, `func_def`, `attribute` helpers). **Dedicated file — not optional.**
- 1.3 Add `GENERIC_TO_SWIFT` dict + `LanguageConfig` entry in `src/utils/type_mapper.py` (Double/Int/String/Bool/Date/TimeInterval/etc.).
- 1.4 Add `@app.command() def swift(...)` in `main.py` with flags `formulas`, `wrappers`, `runtime`, `flatten`, `benchmark`.
- 1.5 Wire `swift` into `main.py all()` command (`--swift-folder`).
- 1.6 Create Swift package skeleton at `myairtable-tests/swift/` — hand-written `Package.swift` (platforms, test target), empty `Sources/MyAirtable/` and `Tests/MyAirtableTests/` placeholders. `Package.swift` is checked into the repo; generator does not overwrite it.
- 1.7 Update `myairtable-tests/build.sh` with `--swift-folder`.
- 1.8 Update `myairtable-tests/test.sh` with `swift` case (`swift test`).
- 1.9 Update `myairtable-tests/checks.sh` with swift-format + `swift build`.
- 1.10 Update `myairtable/checks.sh` with swift-format version check + `swift build` + `swift test` against `tests/swift_static/`.
- 1.11 Create `tests/swift_static/` Swift package for running static-runtime unit tests from main repo.
- 1.12 **Prototype & test @Observable + Codable co-existence** — write a hand-crafted `TestCodableObservableModel.swift` that exercises: `@Observable` class + `let`/`var` fields + manual `CodingKeys` + manual `init(from:)` + manual `encode(to:)` + round-trip round-trip via `JSONEncoder`/`JSONDecoder`. **This is the Phase 0 exit gate.**

**Exit criteria**:

- `uv run main.py swift swift/output` runs and exits 0.
- `swift build` on generated (empty) package succeeds.
- `tests/swift_static/` Swift Testing suite runs green.
- `TestCodableObservableModel.swift` round-trip test passes.

### Feature 2 — Static Runtime Core [P1]

**Purpose**: Hand-written runtime primitives that the generator will copy.
Depends on: Feature 1 (specifically 1.12 prototype informs model template).

- 2.1 `AirtableError.swift` — enum + `Sendable` conformance.
- 2.2 `Types.swift` — `RecordId`, `AirtableAttachment`, `AirtableCollaborator`, `AirtableButton`, `AirtableRecord<T>`, `AirtableThumbnails`, `SortDirection`. All `Sendable` where applicable.
- 2.3 `AirtableClient.swift` — actor; URLSession; bearer auth; retry/backoff; all 6 record endpoints; rate-limit handling.
- 2.4 `AirtableQuery.swift` — `Sendable struct`; `toQueryItems()`.
- 2.5 `Fields.swift` — dual ID/name lookup; `Codable`; `Sendable`.
- 2.6 `DictTable.swift` — struct front-end for raw CRUD (no cache yet — cache integrated in Feature 9).
- 2.7 `CacheStore.swift` — actor skeleton (populated in Feature 9).
- 2.8 Static-runtime unit tests (in `tests/swift_static/Tests/MyAirtableStaticTests/`):
  - `TestAirtableQueryBuild.swift` — query-string encoding for every option.
  - `TestAirtableErrorDecoding.swift` — decode Airtable error JSON bodies.
  - `TestFieldsDualAccess.swift` — verify ID-first, name-fallback lookup.

### Feature 3 — Minimal Generator (dict-only) [P1]

**Purpose**: First end-to-end integration test green (dict CRUD).

- 3.1 `generate_swift()` entry + copy static files to `Sources/MyAirtable/Static/`.
- 3.2 `write_options()` — one Swift `enum` per select-field per table; `Codable` w/ raw string values.
- 3.3 `write_field_types()` — per-table `{Table}Fields` enum/struct with:
  - `static let primaryKeyId: String = "fld123"`
  - `static let primaryKeyName: String = "Primary Key"`
  - `static func idByName(_: String) -> String?`
  - `static func nameById(_: String) -> String?`
  - `static var allIds: [String]`
- 3.4 `write_tables()` (dict-only) — `{Table}Table` struct with `.dict` accessor.
- 3.5 `write_main()` — `Airtable` actor with per-table accessors; `init(apiKey:baseId:)`.
- 3.6 **[removed]** — no `Package.swift` emission (matches other languages).
- 3.7 Offline unit test: generate against `make_test_base(...)` → read file content → assert snippets present. **NOT** shell-out to `swift build` (which requires Swift on PATH).
- 3.8 **Integration test**: `TestStructCrudViaTable.swift` — primary-key-only CRUD via `DictTable` + field-name access sanity.

**Exit criteria**: dict-table CRUD integration test green against real Airtable base.

### Feature 4 — ORM Models (includes offline serialization) [P1]

**Purpose**: Typed record access + all no-network serialization tests green.

- 4.1 `AirtableModel.swift` — protocol (id, createdTime, toRecord, snapshot, dirtyFields, isNew) + `@Observable` base-class pattern.
- 4.2 `OrmTable.swift` — generic typed table; includes **`upsert(_:matchFieldsToMerge:)`** (parity with Rust upsert).
- 4.3 `write_models()` — per-table `@Observable class {Table}Model` + `struct {Table}CreateModel`:
  - Computed fields as `let: T?`; writable as `var: T?`.
  - Manual `CodingKeys` raw-valued to field IDs.
  - Manual `init(from decoder:)` + `encode(to:)` (avoids `@Observable` synthesis issue).
  - `_snapshot` stored property; `snapshot()` / `dirtyFields()` / `toRecord()` methods.
  - `Create{Table}Model` excludes computed fields.
- 4.4 Update `write_tables()` — add `.orm` accessor returning `OrmTable<{Table}Model, Create{Table}Model>`.
- 4.5 Dirty tracking — explicit snapshot dict diff (NOT @Observable-based).
- 4.6 Unit test `TestSwiftComputedFields` in `tests/test_generators.py`. **Specific assertions**:
  - Computed fields emit `let primaryKey: String?` (not `var`).
  - Writable fields emit `var primaryKey: String?` (not `let`).
  - `@Observable` attribute present above class declaration.
  - `CodingKeys` raw values are field IDs (e.g., `case primaryKey = "fld123"`).
  - `Create{Table}Model` struct excludes computed fields.
  - Formula fields generate evaluate method when `runtime=True`.
- 4.7 Unit test `TestSwiftFormulaFunctions` — formula method emission (parity with `TestTypeScriptFormulaFunctions`).
- 4.8 **Offline serialization tests** in `TestSerializing.swift` (no network — moved earlier per critique):
  - `deserialize_simple_fields_by_id`
  - `missing_fields_are_none`
  - `serialize_fields_uses_field_ids`
  - `round_trip_preserves_data`
  - `model_to_json_has_field_values`
  - `model_to_json_skips_none_fields`
  - `model_to_record_has_id_and_fields`
  - `model_to_record_unsaved_has_empty_id` (parity w/ Rust line 69)
- 4.9 **Integration tests**: `TestOrmCrudViaTable.swift`, `TestOrmCrudViaModel.swift`:
  - primary-key-only CRUD
  - all-simple-properties CRUD
  - **upsert_as_create** (parity w/ Rust lines ~549)
  - **upsert_as_update** (parity w/ Rust lines ~580)
  - batch CRUD (111 records, chunked)
  - field-selection via `.fields` param
  - max-records / pagination
  - invalid record ID error handling

### Feature 5 — Complex Field Types [P2]

Depends on Feature 4.

- 5.1 Attachment upload path (matches TypeScript behavior — URL-based).
- 5.2 Collaborator (user) field encode/decode.
- 5.3 Computed field handling — excluded from Create struct; decoded to `let`.
- 5.4 Button field decoding.
- 5.5 **Integration tests**: complex-properties section of ORM CRUD (attachments with async polling, users, computed fields, buttons).

### Feature 6 — Linked Records [P2]

Depends on Feature 4.

- 6.1 `LinkedRecord.swift` — `@dynamicMemberLookup` + `KeyPath<OtherModel, Value>` subscript + async `fetch()` that uses client.
- 6.2 Generator: wire `LinkedRecord<OtherTableModel>` accessors on models (single vs list).
- 6.3 Unit test: chain compiles against synthetic models.
- 6.4 **Integration test**: linked-record traversal (parity w/ TS `linked-records.test.ts`).

### Feature 7 — Formula Builders (filter predicates) [P2]

Depends on Feature 4.

- 7.1 Field-kind formula types in static: `TextFormula`, `NumberFormula`, `DateFormula`, `BooleanFormula`, `SingleSelectFormula`, `MultiSelectFormula`, `LinkFormula`, `IdFormula`, `AttachmentFormula`. Each emits formula string.
- 7.2 Combinators on a neutral struct: `Formulas.and(...)`, `.or(...)`, `.not(_:)`, `.xor(...)`.
- 7.3 `write_formula_helpers()` — per-table `{Table}Filters` struct, accessed via `{Table}Model.f`. Field access: `PrimaryModel.f.primaryKey.equals("x")`.
- 7.4 Unit tests mirror `tests/test_formula.rs` test-by-test (combinators ×8, id ×4, text ×24, single-select ×4, multi-select ×4, number ×10, bool ×4, date ×25, attachment ×3 — ~86 tests).
- 7.5 **Integration test**: `TestFilterByFormula.swift` (parity w/ Rust file).

### Feature 8 — Formula Runtime Transpilation [P2]

Depends on Feature 7 (shares test harness; independent runtime file).

- 8.1 Add `swift` branch to `CodeEmitter` in `src/formulas/formula_transpiler.py`; add `_swift_ident()` keyword-escaper.
- 8.2 `AirtableRuntime.swift` — coercion helpers (`N`, `S`, `A`, `AN`, `AS`).
- 8.3 Math: SUM/AVERAGE/MIN/MAX/ROUND{,UP,DOWN}/CEILING/FLOOR/LOG/EVEN/ODD/VALUE/POWER/MOD/ABS/SQRT/INT — 26 fns.
- 8.4 Logic: IF/SWITCH/IFS/BLANK/TRUE/FALSE/ISERROR/isTruthy — 8 fns.
- 8.5 String: LEFT/RIGHT/MID/LEN/FIND/SEARCH/SUBSTITUTE/REPLACE/LOWER/UPPER/TRIM/REPT/CONCATENATE/ENCODE_URL_COMPONENT — 14+ fns (unicode-aware).
- 8.6 Date/time: D/DATETIME_PARSE/DATESTR/TIMESTR/DATEADD/DATETIME_DIFF/YEAR/MONTH/DAY/HOUR/MINUTE/SECOND/WEEKDAY/WEEKNUM/IS_SAME/IS_BEFORE/IS_AFTER/WORKDAY/WORKDAY_DIFF/SET_TIMEZONE/DATETIME_FORMAT — 21+ fns.
- 8.7 Array: ARRAYJOIN/ARRAYUNIQUE/ARRAYCOMPACT/ARRAYFLATTEN — 4 fns.
- 8.8 Regex: REGEX_EXTRACT/REGEX_MATCH/REGEX_REPLACE/EXP — 4 fns.
- 8.9 Generator wires per-formula-field evaluate methods on model classes.
- 8.10 Python unit tests in `tests/test_formula_transpiler_swift.py` — mirror `test_formula_transpiler.py` for Swift emission.
- 8.11 Swift-side unit tests in `tests/swift_static/Tests/MyAirtableStaticTests/TestAirtableRuntime.swift` — mirror `test_airtable_runtime.rs` (≈180 cases: coercion, math, logic, string, date, array, regex).
- 8.12 **Integration test**: `TestRuntimeFormulas.swift`.

### Feature 9 — Caching [P3]

Depends on Feature 4. Architecture already decided in §2.2.3.

- 9.1 Populate `CacheStore` actor: TTL, LRU cap, per-table wipe, `[CacheKey: CacheEntry]` storage.
- 9.2 Client: `getRecordCached`, `listRecordsCached` delegate to `CacheStore`.
- 9.3 Mutations (create/update/delete) invalidate matching cache keys.
- 9.4 `Airtable.invalidateAllCaches()` + per-table `invalidateCache()`.
- 9.5 **Integration test**: `TestCaching.swift` (≈20 scenarios — parity w/ Rust test_caching.rs).

### Feature 10 — Serialization (integration portion) [P3]

Unit-test portion already landed in Feature 4.8; this feature is **network-bound** serialization tests only.

- 10.1 `TestSerializing.swift` integration cases: linked-records serialize as record-ID arrays; created_time round-trip; id field behavior on unsaved records.

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 1:1 file-by-file diff of each Swift test vs Rust/Python/TS equivalents. File follow-up tasks for gaps.
- 11.2 `./checks.sh` (both repos) green end-to-end.
- 11.3 `./test.sh all` green end-to-end.
- 11.4 `uv run main.py all --swift-folder=…` outputs buildable package alongside other languages.
- 11.5 Confirm Swift-format version pin in CI.

## 6. Dependency Graph (unchanged from v1)

```
Feature 1 ──► Feature 2 ──► Feature 3 ──► Feature 4 ──┬─► Feature 5
                                                       ├─► Feature 6
                                                       ├─► Feature 7 ──► Feature 8
                                                       ├─► Feature 9
                                                       └─► Feature 10
                                                                │
              All ────────────────────────────────────────────► Feature 11
```

## 7. Risks & Mitigations (revised)

| #   | Risk                                          | Mitigation                                                                                                                                 | Phase owned        |
| --- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------ |
| R1  | `@Observable` + `Codable` synthesis collision | Prototype as Feature 1.12 gate; manual Codable in all generated models                                                                     | F1                 |
| R2  | Cache topology vs `Sendable` struct tables    | Cache on actor client, tables forward; decided in §2.2.3                                                                                   | F2 design, F9 impl |
| R3  | Swift 6 strict concurrency                    | All shared state behind actors; `Sendable` explicit on all public types                                                                    | F2 onward          |
| R4  | `LinkedRecord` async ergonomics               | Prototype before generator integration (F6.1)                                                                                              | F6                 |
| R5  | `swift-format` version drift                  | Pin to Swift 6.0 toolchain; version-check step in `checks.sh`                                                                              | F1                 |
| R6  | Formula-transpiler keyword collisions         | `_swift_ident()` helper mirrors `_rust_ident()`                                                                                            | F8                 |
| R7  | Date decode for all Airtable formats          | Custom `JSONDecoder.dateDecodingStrategy` closure; unit-tested                                                                             | F2                 |
| R8  | Batch 111-record test parity                  | Chunk-of-10 helper in `OrmTable`/`DictTable` (matches Rust)                                                                                | F5                 |
| R9  | Swift-Testing parallel execution races        | `@Suite(.serialized)` on integration files                                                                                                 | F1 + F3 onward     |
| R10 | Upsert parity previously missed               | Explicit tasks 4.2 + 4.9                                                                                                                   | F4                 |
| R11 | `swift build` shell-out fragile               | Replace with offline content assertions (F3.7); Swift-side tests live in `tests/swift_static/` Swift package invoked by shell (F1.10–1.11) | F1                 |
| R12 | Swift-format availability on user machine     | `checks.sh` detects + prints install hint; not a hard fail locally                                                                         | F1                 |

## 8. User-Approved Answers (2026-04-16)

| #   | Question                                 | Answer                                                                                                                                                               |
| --- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Swift Testing vs XCTest                  | **Swift Testing**                                                                                                                                                    |
| 2   | Platform minimum (iOS 17 / macOS 14 / …) | OK                                                                                                                                                                   |
| 3   | `swift-format`                           | OK                                                                                                                                                                   |
| 4   | Module name `MyAirtable` (hard-coded)    | OK (not configurable)                                                                                                                                                |
| 5   | Generator emits `Package.swift`          | **NO** — skeleton is hand-written in test repo; other languages don't emit a package manifest either                                                                 |
| 6   | Duration type `TimeInterval`             | Confirmed                                                                                                                                                            |
| 7   | Filter accessor name                     | `PrimaryModel.f.fieldName.equals(...)` — `.f` follows the pattern in other languages                                                                                 |
| 8   | Integration-test concurrency             | Be careful — follow TS/JS pattern: within-file **sequential** (`@Suite(.serialized)`), between-file parallel OK; each file uses distinct keys; cleanup in every test |
| 9   | ORM models vs dict models                | ORM = `@Observable` **class**; dict = `struct`                                                                                                                       |
| 10  | `DictTable` dual ID/name access          | OK                                                                                                                                                                   |

## 9. Exit Criteria (Full Parity)

- [ ] `uv run main.py swift <folder>` generates a buildable Swift package.
- [ ] `uv run main.py all --swift-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) passes with Swift included.
- [ ] `./test.sh all` (myairtable-tests) passes with Swift included.
- [ ] All seven integration test files green (struct/orm crud, serializing, filter, runtime, caching).
- [ ] Unit tests for formula builders + runtime match Rust counts within ±5%.
- [ ] Upsert tests present and green.
- [ ] Dual field-ID/name `DictTable` access tested.
- [ ] `@Observable` + `Codable` confirmed working in production models.
- [ ] Swift code feels idiomatic: actors, `Codable`, `@Observable`, async/await, generics.
