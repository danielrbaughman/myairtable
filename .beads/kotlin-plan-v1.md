# Kotlin Language Support — Implementation Plan v1 (draft)

> Modeled on `.beads/swift-plan-v2.md` (the most recent language addition). Kotlin is the
> sixth target after Python, TypeScript, JavaScript, Rust, and Swift.

## 1. Overview & Goals

Add full-parity Kotlin code generation to `myairtable`, matching the coverage of all
existing targets. Generated Kotlin must feel **idiomatic** — coroutines (`suspend fun`),
`kotlinx.serialization`, sealed classes for sum types, `object` singletons, named/default
arguments, trailing lambdas where natural — not a mechanical port of Swift or Rust.

**Scope:**

- Generator at `myairtable/src/generators/kotlin.py`
- Kotlin writer at `myairtable/src/utils/write_to_kotlin_file.py`
- Static runtime at `myairtable/static/kotlin/`
- Type mapping (`GENERIC_TO_KOTLIN`), formula transpiler Kotlin emitter
- Unit tests: `tests/test_generators.py` Kotlin classes, `tests/test_formula_transpiler_kotlin.py`,
  `tests/kotlin_static/` Gradle test project
- Integration tests at `myairtable-tests/kotlin/` (parity with Swift/Rust/Python/TS)
- CLI wiring (`main.py kotlin` command + `all` integration)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):**

- Kotlin Multiplatform (JVM-only — user-approved)
- Android-specific build artifacts (works as a JVM lib; no AAR)
- Publishing to Maven (no POM emission; mirrors "no Package.swift" decision)
- Flow-based reactive APIs (suspend functions only)

## 2. Design Decisions

### 2.1 User-approved (2026-06-11)

| #   | Question        | Answer                                            |
| --- | --------------- | ------------------------------------------------- |
| 1   | Platform target | **JVM-only** (usable from server JVM and Android) |
| 2   | HTTP + JSON     | **Ktor client + kotlinx.serialization**           |
| 3   | Formatter       | **ktlint** (brew-installable, official style)     |
| 4   | ORM model shape | **Mutable class + snapshot dirty tracking**       |

### 2.2 Core architecture (Swift-pattern → Kotlin idiom mapping)

| Swift construct                           | Kotlin equivalent                                                                  |
| ----------------------------------------- | ---------------------------------------------------------------------------------- |
| `actor AirtableClient` + `URLSession`     | `class AirtableClient` + Ktor `HttpClient`; cache guarded by coroutines `Mutex`    |
| `actor CacheStore`                        | `class CacheStore` with internal `Mutex` (suspend-safe)                            |
| `@Observable class` model, manual Codable | Plain mutable `class` with `var`/`val` + `@Serializable`; `@SerialName` = field ID |
| `enum AirtableJSONValue` (custom sum)     | **kotlinx `JsonElement`** — stdlib-adjacent, idiomatic; no custom JSON sum type    |
| `MaybeSpecialOrError<T>` enum             | `sealed interface MaybeSpecialOrError<T>` + custom `KSerializer` (content-based)   |
| `VecOrValue<T>` enum                      | `sealed interface VecOrValue<T>` + custom `KSerializer` (array-first, fallback)    |
| Select-option `enum: String, Codable`     | `enum class` with `@SerialName` per case; `@Serializable`                          |
| `AirtableError` enum                      | `sealed class AirtableException : Exception` (idiomatic JVM error handling)        |
| `async func` / `await`                    | `suspend fun` (Ktor is coroutine-native; no adapters needed)                       |
| `enum AirtableRuntime` static methods     | `object AirtableRuntime`                                                           |
| `{Table}Model.f` static filter accessor   | `companion object { val f = PrimaryFilters() }` → `PrimaryModel.f.primaryKey.eq()` |
| Backtick keyword escaping                 | Same — Kotlin uses backticks too (`` `object` ``)                                  |
| `RecordId = String` typealias             | `typealias RecordId = String`                                                      |
| `Date` + custom ISO parser                | `java.time.Instant` + custom `AirtableInstantSerializer` (3-format lenient parse)  |
| `TimeInterval` (Double seconds)           | `kotlin.time.Duration` + custom serializer (wire = seconds)                        |

### 2.3 Key decisions needing scrutiny

1. **Package structure**: single flat package `myairtable` for ALL files (static +
   generated), mirroring Swift's single-module no-import simplicity. Generator never emits
   imports for its own types — only stdlib/Ktor/serialization imports. ktlint's
   package-matches-directory rule disabled via `.editorconfig`. (Alternative considered:
   subpackages `myairtable.models` etc. — rejected: forces the generator to compute
   import graphs for little gain in a generated SDK.)

2. **`equals` collision**: Kotlin filter builders cannot overload `equals(Any?)` cleanly —
   `field.equals("x")` resolves against `Any.equals` in some receiver positions and reads
   as identity comparison. Use `eq`/`neq`-style? NO — other languages use `equals`. Kotlin
   CAN declare `fun equals(value: String): Formula` as an overload (different signature);
   it is legal and resolves correctly for non-`Any?` arguments. Keep `equals(...)` for
   cross-language parity; add `infix fun eq` alias only if tests reveal resolution pain.

3. **JsonElement as the type-erased value**: the formula runtime operates on
   `JsonElement?`; transpiler emits `JsonPrimitive(...)`/`JsonNull` constructors and
   `AirtableRuntime.N/S/A/V` coercion helpers. Avoids reinventing Swift's
   `AirtableJSONValue` since kotlinx already ships a JSON sum type.

4. **Serialization is automatic, not manual**: unlike Swift (where `@Observable` broke
   Codable synthesis), Kotlin's `@Serializable` works on mutable classes directly. The
   `_snapshot` map is marked `@Transient`. This removes Swift's biggest risk entirely —
   but adds a **compiler-plugin requirement**: consumers must apply
   `org.jetbrains.kotlin.plugin.serialization`. Documented in generated README header.

5. **Create-model**: match Swift's final shape — no separate Create class. The generated
   model has a constructor with **writable fields only, all defaulting to `null`**
   (idiomatic named-args: `PrimaryModel(primaryKey = "x")`). Serialization of unsaved
   models emits writable fields only (encodeDefaults=false + null-skip policy).

6. **Dirty tracking**: `@Transient private var snapshot: Map<String, JsonElement>` +
   `takeSnapshot()` / `dirtyFields()` diff — direct port of Swift/Rust semantics.

7. **Build tooling bootstrap**: Gradle is NOT installed on the dev machine (Java 24 +
   Kotlin via SDKMAN are). Plan: `sdk install gradle` once, run `gradle wrapper` in each
   Kotlin project, **commit the wrapper** (gradlew + jar). All scripts call `./gradlew`,
   never global `gradle`. Pin Gradle ≥ 8.14 (first version supporting Java 24) and use
   Java **toolchain 21** in build.gradle.kts for library compatibility.

8. **Versions** (pinned exactly in F1): Kotlin 2.1.x, Ktor 3.x, kotlinx.serialization
   1.8.x, kotlinx-coroutines 1.10.x, JUnit 5 + kotlin-test.

9. **Test framework**: JUnit 5 + `kotlin.test` assertions, `kotlinx-coroutines-test`
   `runTest` for suspend tests. Integration CRUD phases use
   `@TestInstance(PER_CLASS)` + `@TestMethodOrder(OrderAnnotation)` to share record IDs
   across ordered methods (the JUnit analog of pytest class variables / vitest closures).
   Within-class sequential (JUnit default); across-class parallelism left OFF initially
   (Gradle default sequential) — distinct primary keys per file still required.

10. **ktlint scope**: format/lint `static/kotlin/`, `tests/kotlin_static/src/`, and
    `myairtable-tests/kotlin/src/` only — never generated `output/` (matches swift-format
    scoping). Install via `brew install ktlint`; checks.sh warns-and-skips if missing.

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/kotlin.py              # NEW ~1000 LOC (mirrors swift.py structure)
src/utils/write_to_kotlin_file.py     # NEW WriteToKotlinFile (KDoc, region, fun/class/object helpers, keyword escape)
src/utils/type_mapper.py              # MOD: GENERIC_TO_KOTLIN + LanguageConfig + map_kotlin_type + apply_kotlin_computed_wrapping
src/utils/write_to_file.py            # MOD: add "kotlin" literal + newline case
src/meta.py                           # MOD: _kotlin_type cache + kotlin_type property
src/formulas/formula_transpiler.py    # MOD: add "kotlin" language + emitter branches (~68 sites)
main.py                               # MOD: `kotlin` command + `all --kotlin-folder`
checks.sh                             # MOD: kotlin section (ktlint + ./gradlew test in tests/kotlin_static)
static/kotlin/                        # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestKotlin* classes (~40 tests, mirror TestSwift*)
tests/test_formula_transpiler_kotlin.py # NEW (mirror swift twin)
tests/kotlin_static/                  # NEW Gradle project for static-runtime unit tests
  ├── settings.gradle.kts / build.gradle.kts / gradlew + wrapper
  └── src/
      ├── main/kotlin/ → srcDir points at ../../static/kotlin (no symlink needed; Gradle srcDir)
      └── test/kotlin/myairtable/
          ├── TestAirtableQueryBuild.kt
          ├── TestAirtableExceptionDecoding.kt
          ├── TestSerializableModel.kt        # the @Serializable mutable-model prototype (F1 gate)
          ├── TestDirtyTracking.kt
          ├── TestCacheStore.kt
          ├── TestDateDecoding.kt
          ├── TestSpecialErrorDecoding.kt
          ├── TestFieldsDualAccess.kt
          ├── TestFormula.kt
          └── TestAirtableRuntime.kt          # ≈180 cases (parity with Rust/Swift)
```

### 3.2 Generated output (per run)

```
kotlin/output/                    # generator does NOT emit build.gradle.kts
├── dynamic/
│   ├── models/{Table}Model.kt
│   ├── options/{Table}Options.kt
│   ├── types/{Table}Fields.kt
│   ├── formulas/{Table}Filters.kt
│   └── tables/{Table}Table.kt
├── static/                        # copied from static/kotlin/
└── Airtable.kt
```

All files declare `package myairtable`.

### 3.3 Test repo (`myairtable-tests`)

```
kotlin/
├── settings.gradle.kts            # HAND-WRITTEN, persists
├── build.gradle.kts               # HAND-WRITTEN: kotlin jvm + serialization plugins, Ktor deps,
│                                  #   sourceSets.main.kotlin.srcDir("output"), JUnit 5
├── gradlew / gradle/wrapper/      # committed wrapper
├── output/                        # regenerated by build.sh
└── src/test/kotlin/myairtable/tests/
    ├── TestSetup.kt               # .env walker + Airtable factory + primaryKey(suite,label) helper
    ├── TestStructCrudViaTable.kt
    ├── TestOrmCrudViaTable.kt
    ├── TestOrmCrudViaModel.kt
    ├── TestSerializing.kt
    ├── TestFilterByFormula.kt
    ├── TestRuntimeFormulas.kt
    ├── TestCaching.kt
    ├── TestLinkedRecords.kt
    ├── TestComplexProperties.kt
    └── TestSpecialErrorDeser.kt
build.sh                           # MOD: --kotlin-folder ./kotlin/output
test.sh                            # MOD: kotlin case (./gradlew -p kotlin test, --filter via --tests)
checks.sh                          # MOD: ktlint + ./gradlew -p kotlin compileTestKotlin
```

## 4. Static Runtime Contract (static/kotlin/)

| File                   | Contents                                                                                                                                                                                                                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AirtableException.kt` | `sealed class AirtableException`: `Http(status, body)`, `Api(code, message)`, `Decoding(cause)`, `InvalidUrl`, `MissingCredentials`, `RateLimited(retryAfterSeconds)`                                                                                                               |
| `AirtableClient.kt`    | Ktor HttpClient (CIO engine), bearer auth, retry w/ backoff on 429, all record endpoints, owns CacheStore, chunk-of-10 batching, `+`→`%2B` query encoding (port Swift fix)                                                                                                          |
| `CacheStore.kt`        | TTL + LRU cache behind `Mutex`; per-table wipe; `invalidateAll()`                                                                                                                                                                                                                   |
| `AirtableModel.kt`     | `interface AirtableModel`: id, createdTime, `toRecord()`, `takeSnapshot()`, `dirtyFields()`, `isNew`                                                                                                                                                                                |
| `AirtableQuery.kt`     | `data class` — formula, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldId; `toParameters()`                                                                                                                                                                           |
| `Fields.kt`            | Wraps `Map<String, JsonElement>` with dual ID/name get/set (ID-first, name fallback)                                                                                                                                                                                                |
| `DictTable.kt`         | Raw CRUD returning `Fields`; mirrors OrmTable API                                                                                                                                                                                                                                   |
| `OrmTable.kt`          | `class OrmTable<T : AirtableModel>` — typed CRUD + `upsert(model, matchFields)`, batch chunking, cache invalidation                                                                                                                                                                 |
| `Formula.kt`           | `Formulas` object combinators (and/or/not/xor) + formula field classes (Text/Number/Date/Boolean/Select/MultiSelect/Link/Id/Attachment)                                                                                                                                             |
| `AirtableRuntime.kt`   | `object` — N/S/A/V coercions + ~80 formula functions (math, logic, string, date via java.time, array, regex)                                                                                                                                                                        |
| `Types.kt`             | `RecordId`, `AirtableAttachment`, `AirtableThumbnails`, `AirtableCollaborator`, `AirtableButton`, `AirtableRecord<T>`, `SortDirection`, `Sort`, `VecOrValue<T>`, `SpecialNumber`, `ErrorValue`, `MaybeSpecialOrError<T>`, `AirtableInstantSerializer`, `AirtableDurationSerializer` |

Estimated ~3,500 LOC (slightly above Swift's 3,126 — custom KSerializers are verbose).

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 Add `"kotlin"` to `WriteToFile.language` literal + newline case.
- 1.2 Create `write_to_kotlin_file.py` (KDoc `/** */`, `// region`, `class/object/enum/fun/val/var` helpers, `_kotlin_ident()` backtick escape, `_choice_to_case()`).
- 1.3 `GENERIC_TO_KOTLIN` + LanguageConfig + `map_kotlin_type()` + `apply_kotlin_computed_wrapping()` + meta.py property.
- 1.4 `main.py kotlin` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--kotlin-folder`).
- 1.6 Bootstrap Gradle: `sdk install gradle`, create `tests/kotlin_static/` project, commit wrapper. Pin versions.
- 1.7 Create `myairtable-tests/kotlin/` Gradle skeleton (hand-written build files + wrapper, `output/` source dir).
- 1.8 Update `myairtable-tests/build.sh` (`--kotlin-folder`).
- 1.9 Update `myairtable-tests/test.sh` (kotlin case + suite filters via `--tests`).
- 1.10 Update `myairtable-tests/checks.sh` (ktlint + compile).
- 1.11 Update `myairtable/checks.sh` (ktlint + `./gradlew test` in tests/kotlin_static; warn-skip if no JVM).
- 1.12 **Prototype gate**: `TestSerializableModel.kt` — mutable `@Serializable` class, `@SerialName` field-ID keys, `@Transient` snapshot, null-skip encode, round-trip. Validates decision §2.3.4–6 before generator templating.

**Exit**: `uv run main.py kotlin <folder>` exits 0 (even with stub output); both Gradle projects compile; prototype test green.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `AirtableException.kt`; 2.2 `Types.kt` (incl. serializers for Instant/Duration/VecOrValue/MaybeSpecialOrError); 2.3 `AirtableClient.kt`; 2.4 `AirtableQuery.kt`; 2.5 `Fields.kt`; 2.6 `DictTable.kt`; 2.7 `CacheStore.kt` skeleton.
- 2.8 Unit tests: TestAirtableQueryBuild, TestAirtableExceptionDecoding, TestFieldsDualAccess, TestDateDecoding, TestSpecialErrorDecoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — **first integration test ASAP**

- 3.1 `generate_kotlin()` entry + static copy.
- 3.2 `write_options()` — `enum class` per select field.
- 3.3 `write_field_types()` — `{Table}Fields` object: per-field Id/Name constants, idByName/nameById, allIds; `{Table}View` enum.
- 3.4 `write_tables()` (dict accessor only).
- 3.5 `write_main()` — `class Airtable(baseId, apiKey, cacheSeconds)` with per-table vals + secondary constructor taking a client.
- 3.6 Offline unit tests (content assertions, no compile shell-out).
- 3.7 **Integration**: `TestStructCrudViaTable.kt` green against real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `AirtableModel.kt` interface; 4.2 `OrmTable.kt` incl. upsert.
- 4.3 `write_models()` — mutable class, writable-only constructor w/ null defaults, `val` computed / `var` writable, `@SerialName` field IDs, snapshot dirty tracking, evaluate methods when runtime=True.
- 4.4 `write_tables()` ORM accessor.
- 4.5 Unit tests `TestKotlinComputedFields` (assertions mirror Swift list: val/var split, @Serializable present, @SerialName IDs, constructor excludes computed, evaluate methods gated).
- 4.6 Offline `TestSerializing.kt` (8 cases — parity list from Swift 4.8).
- 4.7 **Integration**: TestOrmCrudViaTable (incl. upsert-as-create/update, 111-record batch, field selection, maxRecords, invalid-ID), TestOrmCrudViaModel.

### Feature 5 — Complex Field Types [P2]

Attachments (URL-based upload), collaborators, buttons, computed `MaybeSpecialOrError` decoding. Integration: TestComplexProperties + complex sections of CRUD files + TestSpecialErrorDeser.

### Feature 6 — Linked Records [P2]

Raw `List<RecordId>?` on models (Swift/Rust final shape — no wrapper). Integration: TestLinkedRecords (resolve via `airtable.secondary.get(ids)`).

### Feature 7 — Formula Builders [P2]

- 7.1 Formula field classes in static `Formula.kt`; 7.2 combinators; 7.3 `write_formula_helpers()` → `{Table}Filters` + `Model.f` companion val.
- 7.4 Unit tests `TestFormula.kt` (~86 cases mirroring Rust test_formula.rs categories).
- 7.5 **Integration**: TestFilterByFormula.kt.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler: `"kotlin"` language, `_runtime = "AirtableRuntime"`, `_self = "this"`, value constructors emit `JsonPrimitive(...)`; ~68 branch sites.
- 8.2–8.8 `AirtableRuntime.kt` function groups (math 26, logic 8, string 14+, date 21+ via java.time, array 4, regex 4).
- 8.9 Generator wires evaluate methods.
- 8.10 `tests/test_formula_transpiler_kotlin.py` (mirror Swift twin, ~30 tests).
- 8.11 `TestAirtableRuntime.kt` ≈180 cases.
- 8.12 **Integration**: TestRuntimeFormulas.kt.

### Feature 9 — Caching [P3]

CacheStore population (TTL/LRU/invalidation), client cached paths, mutations invalidate. Integration: TestCaching.kt (~10 scenarios, parity w/ Rust).

### Feature 10 — Serialization (integration portion) [P3]

Network-bound serializing cases (linked-record arrays, createdTime round-trip, unsaved-id behavior).

### Feature 11 — Parity Audit & Polish [P3]

File-by-file diff vs Swift/Rust/Python/TS tests; `checks.sh` both repos green; `test.sh all` green; `main.py all` with kotlin alongside others; README updates.

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

| #   | Risk                                                                    | Mitigation                                                                                     |
| --- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| R1  | Gradle not installed; Java 24 compat                                    | F1.6 bootstrap via SDKMAN; commit wrapper; Gradle ≥8.14; toolchain 21                          |
| R2  | `@Serializable` + mutable class + @Transient quirks                     | F1.12 prototype gate before any generator templating                                           |
| R3  | `equals` overload resolution in filter DSL                              | Legal overload; covered by TestFormula compile+string assertions; `eq` alias fallback          |
| R4  | Custom KSerializers (VecOrValue, MaybeSpecialOrError, Instant 3-format) | Dedicated unit tests in F2.8 mirroring Swift TestSpecialErrorDecoding/TestDateDecoding         |
| R5  | ktlint formatting fights generated style                                | ktlint never runs on generated output; only static + tests                                     |
| R6  | JUnit cross-class parallelism racing shared records                     | Parallelism off by default; distinct primary keys per file anyway                              |
| R7  | Ktor 3 API churn                                                        | Pin exact versions in F1; Context7/docs check during F2.3                                      |
| R8  | Transpiler emits invalid Kotlin for edge formulas                       | test_formula_transpiler_kotlin.py + integration TestRuntimeFormulas                            |
| R9  | Gradle cold-start slowness in test.sh loops                             | Gradle daemon enabled by default; configuration cache on                                       |
| R10 | kotlinx encodeDefaults/null-skip semantics for create payloads          | Explicit Json config in client (`encodeDefaults=false, explicitNulls=false`); prototype-tested |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py kotlin <folder>` generates a compiling Kotlin source set.
- [ ] `uv run main.py all --kotlin-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Kotlin included.
- [ ] `./test.sh all` (myairtable-tests) green with Kotlin included.
- [ ] All ten integration test files green (struct/orm crud ×3, serializing, filter, runtime, caching, linked, complex, special-deser).
- [ ] Formula builder + runtime unit-test counts within ±5% of Rust.
- [ ] Upsert + dual ID/name Fields access tested.
- [ ] Generated code is idiomatic Kotlin (suspend, sealed, named args, no Java-isms).
