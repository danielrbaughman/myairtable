# Kotlin Language Support — Implementation Plan v2

> **Changes from v1 (plan-critic round, 2026-06-11)**: fixed the `@Serializable` computed-field
> shape (CRIT-1: computed fields MUST be constructor `val` params — body-only `val`s can't be
> decoded); specified the `V()` coercion helper as `inline reified` + `Json.encodeToJsonElement`
> (CRIT-2); renamed filter method `equals` → `eq`/`neq` (CRIT-3 footgun); added explicit tasks for
> `apply_disambiguated_type`, `is_already_list`, `make_test_base` private-attr dict, and the
> type_mapper `Language` literal (HIGH-1/2); made Ktor `+`-encoding a verify-first task (HIGH-4);
> specified the `JsonDecoder.decodeJsonElement()` peek pattern for VecOrValue/MaybeSpecialOrError
> serializers (MED-3/4); resolved the Duration wire-unit question (MED-2); noted LocalDate→Instant
> conversion requirement (MED-1); JDK-21-toolchain auto-provisioning note (MED-5); test.sh loop +
> tests-repo ktlint guard + F5/F6 integration-task granularity (LOW-1/2/3); corrected transpiler
> branch-site count (~28 guarded blocks, not 68).

## 1. Overview & Goals

Add full-parity Kotlin code generation to `myairtable`, matching the coverage of the existing
Python, TypeScript, JavaScript, Rust, and Swift targets. Generated Kotlin must feel
**idiomatic** — coroutines (`suspend fun`), `kotlinx.serialization`, sealed types for sums,
`object` singletons, named/default arguments — not a mechanical port of Swift or Rust.

**Scope:**

- Generator at `myairtable/src/generators/kotlin.py` + `src/utils/write_to_kotlin_file.py`
- Static runtime at `myairtable/static/kotlin/` (custom Airtable client — no third-party SDK)
- Type mapping (`GENERIC_TO_KOTLIN`) + formula transpiler Kotlin emitter
- Unit tests: `tests/test_generators.py` Kotlin classes, `tests/test_formula_transpiler_kotlin.py`,
  `tests/kotlin_static/` Gradle test project
- Integration tests at `myairtable-tests/kotlin/` (parity with Swift/Rust/Python/TS)
- CLI wiring (`main.py kotlin` + `all --kotlin-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):** Kotlin Multiplatform; Android AAR artifacts; Maven publishing / POM emission
(mirrors "no Package.swift"); Flow-based reactive APIs.

## 2. Design Decisions

### 2.1 User-approved (2026-06-11)

| #   | Question        | Answer                                            |
| --- | --------------- | ------------------------------------------------- |
| 1   | Platform target | **JVM-only** (usable from server JVM and Android) |
| 2   | HTTP + JSON     | **Ktor client + kotlinx.serialization**           |
| 3   | Formatter       | **ktlint** (brew-installable, official style)     |
| 4   | ORM model shape | **Mutable class + snapshot dirty tracking**       |

### 2.2 Swift-pattern → Kotlin idiom mapping

| Swift construct                         | Kotlin equivalent                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------------------- |
| `actor AirtableClient` + `URLSession`   | `class AirtableClient` + Ktor `HttpClient` (CIO); cache guarded by coroutines `Mutex` |
| `actor CacheStore`                      | `class CacheStore` with internal `Mutex` (suspend-safe)                               |
| `@Observable class`, manual Codable     | Mutable `class` + `@Serializable`; `@SerialName` raw values = field IDs               |
| `enum AirtableJSONValue`                | **kotlinx `JsonElement`** — no custom JSON sum type (see §2.3.3)                      |
| `MaybeSpecialOrError<T>` enum           | `sealed interface MaybeSpecialOrError<T>` + custom `KSerializer` (see §2.3.7)         |
| `VecOrValue<T>` enum                    | `sealed interface VecOrValue<T>` + custom `KSerializer` (see §2.3.7)                  |
| Select-option `enum: String, Codable`   | `enum class` with `@SerialName` per case; `@Serializable`                             |
| `AirtableError` enum                    | `sealed class AirtableException : Exception(...)` (idiomatic JVM error handling)      |
| `async func` / `await`                  | `suspend fun` (Ktor is coroutine-native)                                              |
| `enum AirtableRuntime` static methods   | `object AirtableRuntime`                                                              |
| `{Table}Model.f` static filter accessor | `companion object { val f = {Table}Filters() }` → `PrimaryModel.f.primaryKey.eq(...)` |
| Backtick keyword escaping               | Same — Kotlin backticks (`` `object` ``)                                              |
| `RecordId = String` typealias           | `typealias RecordId = String`                                                         |
| `Date` + custom 3-format parser         | `java.time.Instant` + `AirtableInstantSerializer` (§2.3.6)                            |
| `TimeInterval` (Double seconds)         | `kotlin.time.Duration`, wire = **integer seconds** (§2.3.8)                           |

### 2.3 Newly locked (resolving critic issues)

#### 2.3.1 Computed fields are CONSTRUCTOR `val` params (CRIT-1)

kotlinx.serialization decodes **only constructor parameters** (body properties without
`@Transient` fail compilation; with `@Transient` they're never decoded). Therefore the generated
model's primary constructor contains **all** fields:

- computed fields as `val fieldName: T? = null`
- writable fields as `var fieldName: T? = null`

All default to `null`, so idiomatic creation still reads `PrimaryModel(primaryKey = "x")` —
callers simply never pass computed fields (they can, technically; acceptable, matches Rust where
struct literals can set computed fields too). **Create/update payloads never serialize computed
fields**: payload construction does NOT use the model's plugin-generated serializer wholesale —
`toCreateFields()` / `dirtyFields()` build a `JsonObject` from **writable field IDs only**
(snapshot diff for update, non-null writable fields for create), with the client's
`Json { encodeDefaults = false; explicitNulls = false }`. The plugin serializer is used for
**decoding** responses. This trades Swift's `@Observable`-vs-Codable problem for a
constructor-scope constraint — validated by the F1.13 prototype gate before any templating.

#### 2.3.2 Filter DSL uses `eq` / `neq`, not `equals` (CRIT-3)

`fun equals(value: String): Formula` compiles as an overload of `Any.equals`, but
`field.equals(x)` silently resolves to `Any.equals(Any?): Boolean` whenever the argument isn't
statically the overload type — a silent wrong-return-type footgun. Kotlin DSL convention
(Exposed, Ktorm) is `eq`. **Decision**: primary names `eq` / `neq`; all other method names match
the other languages (`contains`, `startsWith`, `greaterThan`, `isEmpty`/`isNotEmpty`, …). This is
a deliberate, documented naming deviation for language-safety reasons.

#### 2.3.3 `JsonElement` is the type-erased value; `V()` is `inline reified` (CRIT-2)

The formula runtime operates on `JsonElement?`. The transpiler emits `JsonPrimitive(...)` /
`JsonNull` for literals. For field references (Swift: `AirtableRuntime.V(self.field)`), Kotlin
needs a generic encoder, which is impossible without reification:

```kotlin
inline fun <reified T> V(value: T?): JsonElement =
    if (value == null) JsonNull else AirtableJson.instance.encodeToJsonElement(value)
```

where `AirtableJson.instance` is the shared `Json` configuration with `Instant`/`Duration`
serializers registered (`serializersModule`). Designed and unit-tested in F2 before the
transpiler work in F8. Coercion helpers `N()` (→ Double), `S()` (→ String), `A()` (→
List<JsonElement>), `D()` (→ Instant) mirror Swift.

#### 2.3.4 Custom KSerializers use the `decodeJsonElement()` peek pattern (MED-3/4)

kotlinx has no `try?`-style fallback decoding. `VecOrValue<T>` and `MaybeSpecialOrError<T>`
serializers cast to `JsonDecoder`, call `decodeJsonElement()`, and dispatch structurally:

- `VecOrValue`: `JsonArray` → `Multiple(List<T?>)`, else → `Single(T)`
- `MaybeSpecialOrError`: object with `"specialValue"` key → `Special`; object with `"error"` key
  → `Error`; else decode as `T` → `Value`

(`JsonContentPolymorphicSerializer`-style; encoding via `encodeJsonElement`.) These therefore
only work with JSON format — acceptable, the client is JSON-only. Round-trip unit tests for
`MaybeSpecialOrError<String>`, `<Double>`, and `VecOrValue<String>` are an F2.8 gate.

#### 2.3.5 Flat package `myairtable`

All files (static + generated) declare `package myairtable` — mirrors Swift's single-module,
zero-self-imports simplicity; generator only emits stdlib/Ktor/serialization imports. Single-
segment packages are precedented (`okhttp3`, `kotlinx.*` roots). ktlint's package-matches-
directory rule disabled via `.editorconfig`. Constraint stated explicitly: static runtime files
also carry `package myairtable`.

#### 2.3.6 Date parsing (MED-1)

`AirtableInstantSerializer` decode order: `Instant.parse()` (fractional + plain ISO) →
`OffsetDateTime.parse().toInstant()` → `LocalDate.parse().atStartOfDay(ZoneOffset.UTC).toInstant()`
(date-only `YYYY-MM-DD` — `Instant.parse` alone rejects it). Encode: ISO-8601 UTC. Unit-test
gate in F2.8 mirroring Swift `TestDateDecoding`.

#### 2.3.7 Serialization architecture summary

- Decode: plugin-generated serializers + custom serializers via `serializersModule` /
  `@Serializable(with=...)` on field types.
- Encode (create/update): hand-rolled `JsonObject` builders over writable fields only (§2.3.1).
- Shared `Json` instance: `ignoreUnknownKeys = true; encodeDefaults = false; explicitNulls = false`.
- Consumers must apply `org.jetbrains.kotlin.plugin.serialization` — documented in generated
  file headers and both hand-written `build.gradle.kts` files prove the setup.

#### 2.3.8 Duration wire unit (MED-2)

Airtable sends duration as **numeric seconds** — confirmed against real data during the Swift
effort (Swift memory: `TimeInterval` seconds, CONFIRMED). The "Milliseconds" comments next to
Rust/TS `DURATION` mappings in type_mapper.py are suspect; Kotlin uses
`Duration` ↔ `value.seconds`. F4/F5 integration tests assert a known duration round-trips with
the right magnitude; if real data contradicts, fix serializer + file a task to correct the
Rust/TS comments.

#### 2.3.9 Build tooling bootstrap (MED-5)

Gradle is NOT installed (Java 24 + Kotlin SDKMAN are). F1: `sdk install gradle`, generate
wrappers, **commit wrapper** (gradlew + jar); scripts only ever call `./gradlew`. Gradle ≥ 8.14
(Java 24 host support). `build.gradle.kts` uses Java toolchain 21 + **foojay-resolver-convention**
plugin so JDK 21 auto-provisions if absent. Kotlin 2.1.x, Ktor 3.x, kotlinx.serialization 1.8.x,
kotlinx-coroutines 1.10.x, JUnit 5 — exact pins recorded in F1.

#### 2.3.10 Other settled choices

| Decision            | Value                                                                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Test framework      | JUnit 5 + kotlin-test assertions; `kotlinx-coroutines-test` `runTest` for suspend tests                                                                 |
| Integration phasing | `@TestInstance(PER_CLASS)` + `@TestMethodOrder(OrderAnnotation)`; lateinit shared IDs                                                                   |
| Test parallelism    | JUnit cross-class parallelism OFF; distinct primary keys per file regardless                                                                            |
| ktlint scope        | `static/kotlin/`, `tests/kotlin_static/src/`, `myairtable-tests/kotlin/src/` — NEVER generated output; warn-and-skip guard in **both** repos' checks.sh |
| File naming         | `PascalCase.kt`; property naming `lowerCamelCase` via `name_camel()`                                                                                    |
| Create-model        | No separate Create class (matches Swift final shape) — constructor with null defaults                                                                   |
| Linked records      | Raw `List<RecordId>?`; resolve via `airtable.<table>.get(ids)` (Swift/Rust final shape)                                                                 |
| Dirty tracking      | `@Transient private var snapshot: Map<String, JsonElement>` + diff (port of Swift/Rust)                                                                 |
| Errors              | `sealed class AirtableException` incl. `RateLimited(retryAfterSeconds)`                                                                                 |
| build.gradle.kts    | **Not emitted by generator** — hand-written in consuming projects (= no Package.swift)                                                                  |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/kotlin.py              # NEW ~1000 LOC (mirrors swift.py structure)
src/utils/write_to_kotlin_file.py     # NEW WriteToKotlinFile (KDoc /** */, // region, class/object/
                                      #   enum/fun/val/var helpers, _kotlin_ident() backtick escape,
                                      #   _choice_to_case())
src/utils/type_mapper.py              # MOD: GENERIC_TO_KOTLIN; "kotlin" in Language literal;
                                      #   LanguageConfig entry; map_kotlin_type();
                                      #   apply_kotlin_computed_wrapping(); is_already_list kotlin
                                      #   case; apply_disambiguated_type kotlin branch
src/utils/write_to_file.py            # MOD: "kotlin" literal + newline case
src/meta.py                           # MOD: _kotlin_type PrivateAttr + kotlin_type property
src/formulas/formula_transpiler.py    # MOD: "kotlin" language; ~28 guarded emitter blocks
main.py                               # MOD: `kotlin` command + `all --kotlin-folder`
checks.sh                             # MOD: kotlin section (ktlint guard + ./gradlew test)
static/kotlin/                        # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestKotlin* classes; make_test_base
                                      #   __pydantic_private__ gains "_kotlin_type": None
tests/test_formula_transpiler_kotlin.py # NEW (mirror Swift twin)
tests/kotlin_static/                  # NEW Gradle project (wrapper committed)
  ├── settings.gradle.kts / build.gradle.kts / gradlew / gradle/wrapper/
  └── src/
      ├── main: sourceSets srcDir → ../../static/kotlin
      └── test/kotlin/myairtable/
          ├── TestSerializableModel.kt   # F1.13 prototype gate
          ├── TestDirtyTracking.kt
          ├── TestAirtableQueryBuild.kt
          ├── TestAirtableExceptionDecoding.kt
          ├── TestCacheStore.kt
          ├── TestDateDecoding.kt
          ├── TestSpecialErrorDecoding.kt   # VecOrValue + MaybeSpecialOrError serializers
          ├── TestFieldsDualAccess.kt
          ├── TestValueCoercion.kt          # V()/N()/S()/A()/D() helpers
          ├── TestFormula.kt                # ~86 builder cases
          └── TestAirtableRuntime.kt        # ≈180 runtime cases
```

### 3.2 Generated output (per run)

```
kotlin/output/                    # generator does NOT emit build files
├── dynamic/
│   ├── models/{Table}Model.kt
│   ├── options/{Table}Options.kt
│   ├── types/{Table}Fields.kt
│   ├── formulas/{Table}Filters.kt
│   └── tables/{Table}Table.kt
├── static/                       # copied from static/kotlin/
└── Airtable.kt
```

All files declare `package myairtable`.

### 3.3 Test repo (`myairtable-tests`)

```
kotlin/
├── settings.gradle.kts            # HAND-WRITTEN, persists (foojay resolver)
├── build.gradle.kts               # HAND-WRITTEN: kotlin("jvm") + kotlin("plugin.serialization"),
│                                  #   Ktor/coroutines/JUnit deps, toolchain 21,
│                                  #   sourceSets.main.kotlin.srcDir("output")
├── gradlew / gradle/wrapper/      # committed
├── output/                        # regenerated by build.sh
└── src/test/kotlin/myairtable/tests/
    ├── TestSetup.kt               # .env walker + Airtable factory + primaryKey(suite, label)
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
test.sh                            # MOD: kotlin case (./gradlew -p kotlin test --tests filters)
                                   #      AND add kotlin to the `for lang in ts js py rs swift` loop
checks.sh                          # MOD: ktlint (command -v guard) + ./gradlew -p kotlin compileTestKotlin
```

## 4. Static Runtime Contract (static/kotlin/, ~3,500 LOC)

| File                   | Contents                                                                                                                                                                                                                                                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AirtableException.kt` | `sealed class`: `Http(status, body)`, `Api(code, message)`, `Decoding(cause)`, `InvalidUrl`, `MissingCredentials`, `RateLimited(retryAfterSeconds)`                                                                                                                                                              |
| `AirtableClient.kt`    | Ktor HttpClient (CIO), bearer auth, 429 retry/backoff, all record endpoints, owns CacheStore, chunk-of-10 batching. **F2.3 verify-first**: confirm Ktor 3 URL encoding of `+` in query params (Swift needed a manual `%2B` force-encode; do NOT assume a mechanical port — test `LEN({f})+1` formula round-trip) |
| `AirtableJson.kt`      | Shared `Json` instance (`ignoreUnknownKeys`, `encodeDefaults=false`, `explicitNulls=false`, serializersModule w/ Instant+Duration) + `inline reified V()` and coercion helpers if not on AirtableRuntime                                                                                                         |
| `CacheStore.kt`        | TTL + LRU behind `Mutex`; per-table wipe; `invalidateAll()`                                                                                                                                                                                                                                                      |
| `AirtableModel.kt`     | `interface`: id, createdTime, `toRecord()`, `takeSnapshot()`, `dirtyFields()`, `isNew`                                                                                                                                                                                                                           |
| `AirtableQuery.kt`     | `data class` — formula, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldId; `toParameters()`                                                                                                                                                                                                        |
| `Fields.kt`            | Wraps `Map<String, JsonElement>`; dual ID/name get/set (ID-first, name fallback)                                                                                                                                                                                                                                 |
| `DictTable.kt`         | Raw CRUD returning `Fields`; mirrors OrmTable API                                                                                                                                                                                                                                                                |
| `OrmTable.kt`          | `class OrmTable<T : AirtableModel>` — typed CRUD + `upsert(model, matchFields)`, batching, cache invalidation                                                                                                                                                                                                    |
| `Formula.kt`           | `Formulas` object combinators (and/or/not/xor) + field classes (Text/Number/Date/Boolean/Select/MultiSelect/Link/Id/Attachment) using `eq`/`neq`                                                                                                                                                                 |
| `AirtableRuntime.kt`   | `object` — V/N/S/A/D coercions + ~80 formula functions (math, logic, string, date via java.time, array, regex)                                                                                                                                                                                                   |
| `Types.kt`             | `RecordId`, `AirtableAttachment(+Thumbnails)`, `AirtableCollaborator`, `AirtableButton`, `AirtableRecord<T>`, `SortDirection`, `Sort`, `VecOrValue<T>`, `SpecialNumber`, `ErrorValue`, `MaybeSpecialOrError<T>`, `AirtableInstantSerializer`, `AirtableDurationSerializer`                                       |

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"kotlin"` in `WriteToFile.language` literal + newline case.
- 1.2 `write_to_kotlin_file.py` (`WriteToKotlinFile` + keyword set + `_kotlin_ident` + `_choice_to_case`).
- 1.3 Type system wiring — ALL of: `GENERIC_TO_KOTLIN`; `"kotlin"` in type_mapper `Language`
  literal; `LanguageConfig` entry; `map_kotlin_type()`; `apply_kotlin_computed_wrapping()`;
  `is_already_list` kotlin case; **`apply_disambiguated_type()` kotlin branch**; meta.py
  `_kotlin_type` PrivateAttr + property; **`make_test_base` `__pydantic_private__` gains
  `"_kotlin_type": None`**.
- 1.4 `main.py kotlin` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--kotlin-folder`).
- 1.6 Bootstrap Gradle (`sdk install gradle`); create `tests/kotlin_static/` project; commit
  wrapper; pin all versions; toolchain 21 + foojay resolver.
- 1.7 `myairtable-tests/kotlin/` Gradle skeleton (hand-written build files + wrapper; `output/` srcDir).
- 1.8 `myairtable-tests/build.sh`: `--kotlin-folder`.
- 1.9 `myairtable-tests/test.sh`: kotlin case with suite filters (`--tests`) **and add `kotlin`
  to the `all` language loop**.
- 1.10 `myairtable-tests/checks.sh`: ktlint with `command -v` warn-skip guard + compile check.
- 1.11 `myairtable/checks.sh`: kotlin section (ktlint guard + `./gradlew test` in tests/kotlin_static;
  warn-skip if no JVM).
- 1.12 `brew install ktlint` + `.editorconfig` (disable package-dir rule).
- 1.13 **Prototype gate** `TestSerializableModel.kt`: mutable `@Serializable` class with computed
  `val` + writable `var` **all in the primary constructor** with null defaults; `@SerialName`
  field-ID keys; `@Transient` snapshot; decode populates computed fields; writable-only
  `JsonObject` payload builder; round-trip. Proves §2.3.1 + §2.3.7 before any templating.

**Exit**: `uv run main.py kotlin <folder>` exits 0 (stub ok); both Gradle projects compile;
prototype green; both checks.sh and test.sh run their kotlin sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `AirtableException.kt`.
- 2.2 `Types.kt` — incl. `AirtableInstantSerializer` (3-format, LocalDate→`atStartOfDay(UTC)`),
  `AirtableDurationSerializer` (seconds), `VecOrValue`/`MaybeSpecialOrError` via
  `decodeJsonElement()` peek pattern (§2.3.4).
- 2.3 `AirtableClient.kt` — **starts with the `+`-encoding verification spike** (§4).
- 2.4 `AirtableQuery.kt`; 2.5 `Fields.kt`; 2.6 `DictTable.kt`; 2.7 `CacheStore.kt` skeleton
  (API surface + Mutex; TTL/LRU population deferred to F9).
- 2.8 `AirtableJson.kt` — shared Json + `inline reified V()` + N/S/A/D (§2.3.3).
- 2.9 Unit tests: TestAirtableQueryBuild, TestAirtableExceptionDecoding, TestFieldsDualAccess,
  TestDateDecoding, TestSpecialErrorDecoding (round-trips for `MaybeSpecialOrError<String>`,
  `<Double>`, `VecOrValue<String>`), TestValueCoercion.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration test ASAP

- 3.1 `generate_kotlin()` entry + static copy (exclude AirtableRuntime.kt / Formula.kt per flags).
- 3.2 `write_options()` — `enum class` per select field; dedup collisions (v2/v3 suffix parity).
- 3.3 `write_field_types()` — `{Table}Fields` object (per-field Id/Name constants, idByName /
  nameById, allIds) + `{Table}View` enum.
- 3.4 `write_tables()` (dict accessor only).
- 3.5 `write_main()` — `class Airtable(baseId, apiKey, cacheSeconds)` per-table vals + client ctor.
- 3.6 Offline unit tests (content assertions; no compile shell-out).
- 3.7 **Integration**: `TestStructCrudViaTable.kt` green against the real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `AirtableModel.kt` interface; 4.2 `OrmTable.kt` incl. `upsert`.
- 4.3 `write_models()` — constructor-only properties per §2.3.1; `@SerialName` field IDs;
  snapshot dirty tracking; KDoc per field; evaluate methods when runtime=True.
- 4.4 `write_tables()` ORM accessor.
- 4.5 Unit tests `TestKotlinComputedFields`: computed = `val` ctor param / writable = `var` ctor
  param; `@Serializable` + `@SerialName` IDs present; payload builders exclude computed;
  evaluate methods gated on runtime flag.
- 4.6 Offline `TestSerializing.kt` (8 parity cases from the Swift 4.8 list).
- 4.7 **Integration**: TestOrmCrudViaTable (primary-key-only, all-simple-props,
  upsert-as-create/update, 111-record batch, field selection, maxRecords, invalid-ID error),
  TestOrmCrudViaModel (save/delete paths).

### Feature 5 — Complex Field Types [P2]

- 5.1 Attachment upload (URL-based, TS parity); 5.2 collaborator encode/decode; 5.3 computed
  `MaybeSpecialOrError` end-to-end decode; 5.4 button decode; 5.5 duration round-trip magnitude
  assertion (§2.3.8).
- 5.6 **Integration**: TestComplexProperties.kt + complex sections of CRUD files.
- 5.7 **Integration**: TestSpecialErrorDeser.kt (parity w/ Rust/Swift).

### Feature 6 — Linked Records [P2]

- 6.1 Generator: raw `List<RecordId>?` fields (no wrapper).
- 6.2 **Integration**: TestLinkedRecords.kt — link arrays + resolution via `airtable.secondary.get(ids)`.

### Feature 7 — Formula Builders [P2]

- 7.1 Field classes in `Formula.kt` (`eq`/`neq` per §2.3.2); 7.2 combinators; 7.3
  `write_formula_helpers()` → `{Table}Filters` + companion `f`.
- 7.4 Unit tests `TestFormula.kt` (~86 cases mirroring Rust categories: combinators 8, id 4,
  text 24, single-select 4, multi-select 4, number 10, bool 4, date 25, attachment 3).
- 7.5 **Integration**: TestFilterByFormula.kt.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler: `"kotlin"` in Language literal; `_runtime = "AirtableRuntime"`,
  `_self = "this"`; Kotlin arms in all ~28 guarded emitter blocks (literals, FieldRef → `V()`,
  AND/OR/NOT/XOR, IF/IFS/SWITCH, LEN/BLANK/TRUE/FALSE/RECORD_ID, \_emit_str/\_emit_num/
  \_emit_eq_operand/\_emit_binary_op/\_emit_unary_op, runtime-call fallthrough); `_kotlin_ident`
  escaping.
- 8.2–8.8 `AirtableRuntime.kt` groups: math 26, logic 8, string 14+, date 21+ (java.time),
  array 4, regex 4.
- 8.9 Generator wires evaluate methods on models.
- 8.10 `tests/test_formula_transpiler_kotlin.py` (mirror Swift twin).
- 8.11 `TestAirtableRuntime.kt` ≈180 cases (parity w/ Rust/Swift).
- 8.12 **Integration**: TestRuntimeFormulas.kt.

### Feature 9 — Caching [P3]

- 9.1 CacheStore TTL/LRU/per-table wipe; 9.2 client cached read paths; 9.3 mutation
  invalidation; 9.4 `invalidateAllCaches()` + per-table invalidate.
- 9.5 **Integration**: TestCaching.kt (~10 scenarios, Rust parity).

### Feature 10 — Serialization (integration portion) [P3]

- 10.1 Network-bound TestSerializing cases: linked-record ID arrays, createdTime round-trip,
  unsaved-id behavior.

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 File-by-file test diff vs Swift/Rust/Python/TS; file follow-ups for gaps.
- 11.2 `./checks.sh` both repos green; 11.3 `./test.sh all` green; 11.4 `main.py all` with
  kotlin alongside others; 11.5 README updates (both repos).

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

| #   | Risk                                                 | Mitigation                                                               |
| --- | ---------------------------------------------------- | ------------------------------------------------------------------------ |
| R1  | Computed-field decode vs create-payload exclusion    | §2.3.1 constructor design + hand-rolled payload builders; F1.13 gate     |
| R2  | `V()` generic encoding for Instant/Duration fields   | §2.3.3 `inline reified` + serializersModule; TestValueCoercion in F2     |
| R3  | Gradle absent; Java 24 host                          | SDKMAN bootstrap; committed wrapper; Gradle ≥8.14; toolchain 21 + foojay |
| R4  | VecOrValue/MaybeSpecialOrError serializer complexity | §2.3.4 peek pattern; F2.9 round-trip gates                               |
| R5  | Ktor `+` query encoding corrupts formulas            | F2.3 verify-first spike; integration formula round-trip test             |
| R6  | Duration wire unit ambiguity (seconds vs ms)         | §2.3.8 — seconds (Swift-confirmed); F5.5 magnitude assertion             |
| R7  | `eq` naming deviation surprises cross-language users | Documented in §2.3.2 + generated KDoc; everything else name-matched      |
| R8  | ktlint fights generated style / missing binary       | Never lint generated output; `command -v` guards in BOTH repos           |
| R9  | JUnit cross-class parallelism racing shared records  | Parallelism off; distinct primary keys per file                          |
| R10 | Ktor 3 API churn                                     | Exact pins in F1; docs check during F2.3                                 |
| R11 | Transpiler emits invalid Kotlin for edge formulas    | test_formula_transpiler_kotlin.py + TestRuntimeFormulas integration      |
| R12 | Gradle cold-start slowness in test.sh                | Daemon + configuration cache on                                          |
| R13 | Disambiguated lookup/rollup fields skip Kotlin types | F1.3 explicit `apply_disambiguated_type` task + unit test                |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py kotlin <folder>` generates a compiling Kotlin source set.
- [ ] `uv run main.py all --kotlin-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Kotlin included.
- [ ] `./test.sh all` (myairtable-tests) green with Kotlin included.
- [ ] All ten integration test files green (struct/orm crud ×3, serializing, filter, runtime,
      caching, linked, complex, special-deser).
- [ ] Formula builder + runtime unit-test counts within ±5% of Rust.
- [ ] Upsert + dual ID/name Fields access tested.
- [ ] Generated code is idiomatic Kotlin (suspend, sealed types, named args, no Java-isms).
