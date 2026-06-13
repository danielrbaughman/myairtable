# Java Language Support — Implementation Plan v1

## 1. Overview & Goals

Add full-parity **Java** code generation to `myairtable` — the seventh target, alongside
Python, TypeScript, JavaScript, Rust, Swift, and Kotlin. The closest template is the Kotlin
target (completed 2026-06-12, epic `myairtable-kxrj`): same JVM, same Gradle/JDK-21
infrastructure, same test-base semantics. But the generated code must feel **idiomatic Java**
— not Kotlin-with-semicolons: JavaBeans accessors, generated builders, sealed
interfaces + records + pattern-matching switch for sum types, unchecked exception hierarchy,
plain blocking methods (virtual-thread friendly), Jackson for JSON.

**Scope:**

- Generator at `src/generators/java.py` + `src/utils/write_to_java_file.py`
- Static runtime at `static/java/` (custom Airtable client — JDK HttpClient + Jackson; no
  third-party Airtable SDK)
- Type mapping (`GENERIC_TO_JAVA`) + formula transpiler Java emitter
- Unit tests: `tests/test_generators.py` Java classes, `tests/test_formula_transpiler_java.py`,
  `tests/java_static/` Gradle test project
- Integration tests at `myairtable-tests/java/` (parity with Kotlin/Swift/Rust/TS)
- CLI wiring (`main.py java` + `all --java-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):** Maven publishing / POM emission (mirrors no-Package.swift /
no-build.gradle.kts); CompletableFuture async variants; Android compatibility below 21;
module-info.java (JPMS); annotation-processor integration (Lombok etc. — generator writes
everything explicitly).

## 2. Design Decisions

### 2.1 User-approved (2026-06-12)

| #   | Question     | Answer                                                   |
| --- | ------------ | -------------------------------------------------------- |
| 1   | Java version | **Java 21 LTS** (toolchain 21, same as Kotlin)           |
| 2   | Build tool   | **Gradle** (committed wrapper, foojay resolver, JUnit 5) |
| 3   | HTTP + JSON  | **JDK `java.net.http.HttpClient` + Jackson databind**    |
| 4   | API style    | **Synchronous blocking** (virtual-thread friendly)       |

### 2.2 Kotlin-pattern → Java idiom mapping

| Kotlin construct                                   | Java equivalent                                                                                                                    |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `class AirtableClient` + Ktor + coroutines `Mutex` | `final class AirtableClient` + `java.net.http.HttpClient` + `ReentrantLock`                                                        |
| `@Serializable` class, `@SerialName` = field ID    | Mutable POJO + Jackson `@JsonProperty` (field-ID raw values), field-access mode                                                    |
| kotlinx `JsonElement`                              | Jackson `JsonNode` (type-erased formula/runtime value)                                                                             |
| `sealed interface VecOrValue<T>` + KSerializer     | `sealed interface VecOrValue<T> permits Single, Multiple` (nested records) + custom `JsonDeserializer` w/ `ContextualDeserializer` |
| `sealed interface MaybeSpecialOrError<T>`          | Same pattern: nested records `Value<T>` / `Special<T>` / `Error<T>`                                                                |
| Select-option `enum class` + `@SerialName`         | `enum` with private `value` field + `@JsonValue` / `@JsonCreator`                                                                  |
| `sealed class AirtableException : Exception`       | `sealed abstract class AirtableException extends RuntimeException permits …` (**unchecked**)                                       |
| `suspend fun`                                      | Plain blocking method (callers may wrap in virtual threads)                                                                        |
| `object AirtableRuntime`                           | `public final class AirtableRuntime` with static methods, private ctor                                                             |
| `companion object { val f }` filter accessor       | `public static final PrimaryFilters f = new PrimaryFilters();` → `PrimaryModel.f.primaryKey.eq(...)`                               |
| Backtick keyword escaping                          | **No escape mechanism in Java** — `_java_ident()` renames reserved words with `_` suffix (`class` → `class_`)                      |
| `typealias RecordId = String`                      | No typealias in Java — use plain `String`; `RecordId` appears only in docs                                                         |
| `java.time.Instant` + AirtableInstantSerializer    | Same `Instant`; custom Jackson `JsonDeserializer<Instant>` (3-format)                                                              |
| `kotlin.time.Duration` (wire = seconds)            | `java.time.Duration`; custom (de)serializer, wire = **numeric seconds** (confirmed in Swift/Kotlin work)                           |
| Named/default args for creation                    | **Generated nested `Builder`** (writable fields only) + standard setters                                                           |

### 2.3 Java-specific decisions

#### 2.3.1 Model shape: mutable POJO + getters/setters + Builder

```java
public final class PrimaryModel implements AirtableModel {
    /** Single Line Text {@code fldXXX} */
    @JsonProperty("fldXXX")
    private String singleLineText;          // writable: getter + setter

    /** Auto Number {@code fldYYY} — read-only */
    @JsonProperty("fldYYY")
    private MaybeSpecialOrError<Long> autoNumber;  // computed: getter ONLY

    public String getSingleLineText() { ... }
    public void setSingleLineText(String v) { ... }
    public MaybeSpecialOrError<Long> getAutoNumber() { ... }

    public static Builder builder() { ... }
    public static final class Builder { /* writable-field methods only */ }
}
```

- Jackson configured for **field access** (`PropertyAccessor.FIELD = ANY`, getters/setters
  `NONE`) so `@JsonProperty` lives once, on the field. Computed fields are decode-only by
  construction: Jackson sets the private field; no setter exists.
- Create/update payloads are **hand-rolled** (`toCreateFields()` / `dirtyFields()` returning
  Jackson `ObjectNode` over writable field IDs only) — port of the Kotlin §2.3.1 design.
  The mapper is used wholesale only for **decoding**.
- Dirty tracking: `@JsonIgnore private Map<String, JsonNode> snapshot` + diff
  (`takeSnapshot()` after fetch/save; `dirtyFields()` compares current writable values).
- Boolean getter naming: uniform `getX()` (fields are boxed `Boolean`, where `isX()` is not
  the convention).

#### 2.3.2 Filter DSL keeps `eq` / `neq`

Java has the same footgun as Kotlin (CRIT-3): `equals(Object)` exists on every class, so a
generated `equals(String)` overload silently binds to `Object.equals` (returning `boolean`,
not `Formula`) for non-String arguments. Keep `eq`/`neq`; all other names match other
languages (`contains`, `startsWith`, `greaterThan`, `isEmpty`/`isNotEmpty`, …). This also
gives cross-JVM consistency with the Kotlin target.

#### 2.3.3 `JsonNode` is the type-erased value; `V()` needs no reification

The formula runtime operates on `JsonNode` (Jackson). The transpiler emits
`AirtableRuntime.V(...)` for field refs and Jackson node factories for literals. Unlike
Kotlin, Java needs no `inline reified`:

```java
public static JsonNode V(Object value) {
    return value == null ? NullNode.getInstance() : AirtableJson.MAPPER.valueToTree(value);
}
```

`valueToTree` dispatches on runtime type, so the shared `ObjectMapper` (with
Instant/Duration serializers registered) handles every field type. Coercion helpers
`N()` (→ double), `S()` (→ String), `A()` (→ ArrayNode), `D()` (→ Instant) mirror
Kotlin/Swift.

#### 2.3.4 Custom deserializers use the `readTree` peek + `ContextualDeserializer` pattern

Jackson's analog of the Kotlin `decodeJsonElement()` peek: a `JsonDeserializer<T>` that
reads the subtree as `JsonNode`, dispatches structurally, then converts the payload with
the captured element type. **The element type `T` must be captured via
`ContextualDeserializer.createContextual()`** (Jackson's mechanism for generics — this is
the Java equivalent of the Kotlin typeArg serializer and is the trickiest serialization
piece; it gets a prototype gate):

- `VecOrValue<T>`: `JsonNode.isArray()` → `Multiple(List<T>)`, else → `Single(T)`
- `MaybeSpecialOrError<T>`: object with `"specialValue"` → `Special`; object with
  `"error"` → `Error`; else convert to `T` → `Value`

Registered via `@JsonDeserialize(using = …)` on the sealed interfaces. JSON-format-only
is acceptable (client is JSON-only). Round-trip unit tests for `MaybeSpecialOrError<String>`,
`<Double>`, `VecOrValue<String>`, and the nested `VecOrValue<MaybeSpecialOrError<String>>`
are an F1 prototype gate (the nested case is what computed lookup/rollup fields use).

#### 2.3.5 Flat package `myairtable`; one public type per file

All files (static + generated) declare `package myairtable;`. **Verify-first gate**: javac
requires `public class X` in file `X.java`, but package-vs-directory mismatch is fine when
Gradle passes explicit source lists (it disables sourcepath). F1 prototype proves
`output/dynamic/models/PrimaryModel.java` with `package myairtable;` compiles under
`sourceSets.main.java.srcDir("output")`. Fallback if it fails: generator emits everything
under a `myairtable/` directory root.

Kotlin's multi-type files (Types.kt, 14 top-level types) split into one-file-per-public-type
in Java; closely-coupled small types nest inside their parent (e.g. `Single`/`Multiple`
records nest in `VecOrValue`; `Thumbnail` nests in `AirtableThumbnails`).

#### 2.3.6 Date / Duration / numbers

- `AirtableDateParser` port: `Instant.parse()` → `OffsetDateTime.parse().toInstant()` →
  `LocalDate.parse().atStartOfDay(ZoneOffset.UTC).toInstant()`. Custom Jackson module
  (`AirtableJacksonModule`) registers Instant + Duration (de)serializers on the shared mapper.
- Duration wire unit: **seconds** (locked by Swift/Kotlin live verification).
- Airtable `number` fields are ALWAYS `Double` (never `Long`) — Kotlin learning; tests use
  `42.0`. `autoNumber`/`count` map to `Long` as in Kotlin's `GENERIC_TO_KOTLIN`.
- **JVM `Math.exp(1.0)` is one ULP above V8's `Math.E`** — port Kotlin's pinned
  `EXP(1.0) == Math.E` special case verbatim (same JVM, same bug class).

#### 2.3.7 Errors: unchecked sealed hierarchy

`public sealed abstract class AirtableException extends RuntimeException permits
HttpException, ApiException, DecodingException, InvalidUrlException,
MissingCredentialsException, RateLimitedException` (nested or sibling final classes;
`RateLimitedException` carries `retryAfterSeconds`). Unchecked because checked exceptions
would poison every generated signature — modern Java library idiom (Spring, java.net.http
follow suit). Pattern-matching `switch` over the sealed hierarchy works in tests.

#### 2.3.8 Concurrency

Plain blocking client. `CacheStore` guards its maps with `ReentrantLock` (or
`synchronized` blocks); the client itself is stateless apart from the cache and the
`HttpClient` (which is thread-safe). 429 retry/backoff uses `Thread.sleep` — fine on
virtual threads. No executor ownership; callers control threading.

#### 2.3.9 URL encoding verify-first

Query strings are hand-assembled with `URLEncoder.encode(v, UTF_8)` (form encoding:
`+` → `%2B`, space → `+`). That should match Ktor's behavior (which worked against
Airtable), but the Swift incident makes this a **verify-first spike**: round-trip a
`LEN({field})+1` formula against the real base before building on it. Note
`URLEncoder` is form-encoding, not RFC 3986 — table names in the **path** segment need
`%20` for spaces, not `+`; encode path and query differently (port the Kotlin/Swift
`tableURL` logic and pin with a unit test).

#### 2.3.10 Formatter & lint

`google-java-format` (brew-installable) with `command -v` warn-skip guards in BOTH repos'
checks.sh — exact ktlint pattern. Scope: `static/java/`, `tests/java_static/src/`,
`myairtable-tests/java/src/` — NEVER generated output. The generator's emitted style
should be close to google-java-format so the runtime files stay stable under formatting.

#### 2.3.11 Other settled choices

| Decision            | Value                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| Test framework      | JUnit 5 (`org.junit.jupiter`), plain assertions (`Assertions.*`)                                   |
| Integration phasing | `@TestInstance(PER_CLASS)` + `@TestMethodOrder(OrderAnnotation)`; shared fields for IDs            |
| Test parallelism    | Cross-class parallelism OFF; distinct primary keys per file (`"Java StructCrud PKOnly {ts}"`)      |
| File naming         | `PascalCase.java` (forced: public type = filename); properties `lowerCamelCase` via `name_camel()` |
| Select-option enums | Constants SCREAMING_SNAKE_CASE via `_choice_to_entry()` port; `@JsonValue`-style raw value         |
| Create-model        | No separate Create class — `new {Table}Model()` + setters, or generated `Builder`                  |
| Linked records      | Raw `List<String>` record IDs; resolve via `airtable.secondary().get(ids)`                         |
| Dirty tracking      | `@JsonIgnore` snapshot map + diff (port of Kotlin/Swift/Rust)                                      |
| Table accessors     | `airtable.primary()` methods (Java has no top-level `val` properties)                              |
| build.gradle.kts    | NOT emitted by generator — hand-written in consuming projects                                      |
| Gradle wrapper      | Committed in both `tests/java_static/` and `myairtable-tests/java/` (Gradle 9.x, same as Kotlin)   |
| Javadoc             | `/** … */` with `{@code …}` for field IDs; formula text in `<pre>{@code …}</pre>`                  |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/java.py                # NEW ~1000 LOC (mirrors kotlin.py structure)
src/utils/write_to_java_file.py       # NEW WriteToJavaFile (Javadoc, region comments, class/enum/
                                      #   method/field helpers, _java_ident() underscore-suffix
                                      #   rename, _choice_to_entry(), _java_string_literal())
src/utils/type_mapper.py              # MOD: GENERIC_TO_JAVA; "java" in Language literal;
                                      #   LanguageConfig entry (list_fmt="List<{0}>",
                                      #   union_fmt="VecOrValue<{0}>"); map_java_type();
                                      #   apply_java_computed_wrapping(); is_already_list java
                                      #   case; apply_disambiguated_type java branch
src/utils/write_to_file.py            # MOD: "java" literal + header case
src/meta.py                           # MOD: _java_type PrivateAttr + java_type property
src/formulas/formula_transpiler.py    # MOD: "java" language; Java arms in ~28 guarded blocks
main.py                               # MOD: `java` command + `all --java-folder`
checks.sh                             # MOD: java section (google-java-format guard +
                                      #   ./gradlew test in tests/java_static)
static/java/                          # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestJava* classes; make_test_base
                                      #   __pydantic_private__ gains "_java_type": None
tests/test_formula_transpiler_java.py # NEW (mirror Kotlin twin)
tests/java_static/                    # NEW Gradle project (wrapper committed)
  ├── settings.gradle.kts / build.gradle.kts / gradlew / gradle/wrapper/
  └── src/
      ├── main: sourceSets srcDir → ../../static/java
      └── test/java/myairtable/
          ├── TestPojoModel.java           # F1 prototype gate (§2.3.1/2.3.4/2.3.5)
          ├── TestDirtyTracking.java
          ├── TestAirtableQueryBuild.java
          ├── TestAirtableExceptionDecoding.java
          ├── TestCacheStore.java
          ├── TestClientCachePolicy.java
          ├── TestClientHardening.java
          ├── TestClientUrlEncoding.java
          ├── TestDateDecoding.java
          ├── TestSpecialErrorDecoding.java
          ├── TestFieldsDualAccess.java
          ├── TestValueCoercion.java
          ├── TestTableBoundedOps.java
          ├── TestFormula.java             # ~86 builder cases
          └── TestAirtableRuntime.java     # ≈180 runtime cases
```

### 3.2 Generated output (per run)

```
java/output/                      # generator does NOT emit build files
├── dynamic/
│   ├── models/{Table}Model.java
│   ├── options/{Table}Options.java
│   ├── types/{Table}Fields.java
│   ├── formulas/{Table}Filters.java
│   └── tables/{Table}Table.java
├── static/                       # copied from static/java/
└── Airtable.java
```

All files declare `package myairtable;` (§2.3.5 gate).

### 3.3 Test repo (`myairtable-tests`)

```
java/
├── settings.gradle.kts            # HAND-WRITTEN (foojay resolver)
├── build.gradle.kts               # HAND-WRITTEN: java plugin, toolchain 21, Jackson + JUnit5
│                                  #   deps, sourceSets.main.java.srcDir("output")
├── gradle.properties              # configuration-cache + caching on
├── gradlew / gradle/wrapper/      # committed
├── output/                        # regenerated by build.sh
└── src/test/java/myairtable/tests/
    ├── TestHarness.java           # smoke: generated VERSION constant reachable
    ├── TestSetup.java             # .env walker + Airtable factory + primaryKey(suite, label)
    ├── TestStructCrudViaTable.java
    ├── TestOrmCrudViaTable.java
    ├── TestOrmCrudViaModel.java
    ├── TestSerializing.java
    ├── TestFilterByFormula.java
    ├── TestRuntimeFormulas.java
    ├── TestCaching.java
    ├── TestLinkedRecords.java
    ├── TestComplexProperties.java
    └── TestSpecialErrorDeser.java
build.sh                           # MOD: --java-folder ./java/output
test.sh                            # MOD: java case (cd java && ./gradlew test --tests filters)
                                   #      AND add java to the `for lang in …` all-loop
checks.sh                          # MOD: google-java-format (command -v guard) +
                                   #      (cd java && ./gradlew compileTestJava)
```

## 4. Static Runtime Contract (static/java/, ~25 files, ~4,000 LOC)

One public type per file (Java requirement). Nested types noted inline.

| File                                                | Contents                                                                                                                                                                       |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `AirtableException.java`                            | sealed abstract base + nested/sibling finals: Http, Api, Decoding, InvalidUrl, MissingCredentials, RateLimited(retryAfterSeconds) — unchecked (§2.3.7)                         |
| `AirtableClient.java`                               | JDK HttpClient, bearer auth, 429 retry/backoff, all record endpoints, owns CacheStore, chunk-of-10 batching; path-vs-query encoding (§2.3.9 verify-first)                      |
| `AirtableJson.java`                                 | Shared `ObjectMapper` (fail-on-unknown OFF, field access, NON_NULL inclusion, AirtableJacksonModule) + `V()`/`N()`/`S()`/`A()`/`D()` coercions if not on AirtableRuntime       |
| `AirtableJacksonModule.java`                        | Module registering Instant (3-format) + Duration (seconds) (de)serializers                                                                                                     |
| `AirtableDateParser.java`                           | 3-format parse port                                                                                                                                                            |
| `CacheStore.java`                                   | TTL + LRU behind ReentrantLock; per-table wipe; invalidateAll()                                                                                                                |
| `AirtableModel.java`                                | interface: getId/setId, getCreatedTime, toRecord(), takeSnapshot(), dirtyFields(), isNew()                                                                                     |
| `AirtableQuery.java`                                | builder-style query — formula, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldId; toParameters()                                                                 |
| `Fields.java`                                       | Wraps `Map<String, JsonNode>`; dual ID/name get/set (ID-first, name fallback)                                                                                                  |
| `DictTable.java`                                    | Raw CRUD returning Fields; mirrors OrmTable API                                                                                                                                |
| `OrmTable.java`                                     | `OrmTable<T extends AirtableModel>` — typed CRUD + upsert(model, matchFields), batching, cache invalidation                                                                    |
| `Formula.java` (+ field classes)                    | `Formulas` combinators (and/or/not/xor) + Text/Number/Date/Boolean/Select/MultiSelect/Link/Id/Attachment field classes using eq/neq — may split into `formula/` files if large |
| `AirtableRuntime.java`                              | final class, static methods — V/N/S/A/D + ~80 formula functions (math incl. EXP pin, logic, string, date via java.time, array, regex)                                          |
| `VecOrValue.java`                                   | sealed interface + nested records Single/Multiple + ContextualDeserializer (§2.3.4)                                                                                            |
| `MaybeSpecialOrError.java`                          | sealed interface + nested records Value/Special/Error + ContextualDeserializer                                                                                                 |
| `SpecialNumber.java` / `ErrorValue.java`            | records (`{"specialValue": …}` / `{"error": …}`)                                                                                                                               |
| `AirtableRecord.java`                               | generic record envelope (id, createdTime, fields)                                                                                                                              |
| `AirtableAttachment.java`                           | + nested Thumbnails/Thumbnail                                                                                                                                                  |
| `AirtableCollaborator.java` / `AirtableButton.java` | data carriers                                                                                                                                                                  |
| `Sort.java` / `SortDirection.java`                  | sort spec + enum                                                                                                                                                               |
| `MyAirtableRuntimeInfo.java`                        | VERSION constant                                                                                                                                                               |

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"java"` in `WriteToFile.language` literal + header case.
- 1.2 `write_to_java_file.py` (`WriteToJavaFile` + reserved-word set incl. literals/`_` +
  `_java_ident()` `_`-suffix rename + `_choice_to_entry()` + `_java_string_literal()`).
- 1.3 Type system wiring — ALL of: `GENERIC_TO_JAVA`; `"java"` in type_mapper `Language`
  literal; `LanguageConfig` entry; `map_java_type()`; `apply_java_computed_wrapping()`;
  `is_already_list` java case; `apply_disambiguated_type()` java branch; meta.py
  `_java_type` PrivateAttr + property; `make_test_base` `__pydantic_private__` gains
  `"_java_type": None`.
- 1.4 `main.py java` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--java-folder`).
- 1.6 `tests/java_static/` Gradle project (wrapper committed; java plugin; toolchain 21 +
  foojay; Jackson + JUnit 5 pins).
- 1.7 `myairtable-tests/java/` Gradle skeleton (hand-written build files + wrapper;
  `output/` srcDir).
- 1.8 `myairtable-tests/build.sh`: `--java-folder`.
- 1.9 `myairtable-tests/test.sh`: java case with suite filters AND add `java` to the
  `all` language loop.
- 1.10 `myairtable-tests/checks.sh`: google-java-format with `command -v` guard +
  compileTestJava check.
- 1.11 `myairtable/checks.sh`: java section (format guard + `./gradlew test` in
  tests/java_static; warn-skip if no JVM).
- 1.12 `brew install google-java-format`.
- 1.13 **Prototype gate** `TestPojoModel.java`: POJO with `@JsonProperty` field-ID keys,
  field-access mapper config, computed field decode-only, `@JsonIgnore` snapshot,
  writable-only ObjectNode payload builders, round-trip; PLUS `ContextualDeserializer`
  round-trips for `VecOrValue`/`MaybeSpecialOrError` incl. nested composition; PLUS
  package-vs-directory compile proof (§2.3.5). Proves all three risky foundations before
  any templating.

**Exit**: `uv run main.py java <folder>` exits 0 (stub ok); both Gradle projects compile;
prototype green; both checks.sh and test.sh run their java sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `AirtableException.java` hierarchy.
- 2.2 Types: `VecOrValue`, `MaybeSpecialOrError`, `SpecialNumber`, `ErrorValue`,
  `AirtableRecord`, `AirtableAttachment`, `AirtableCollaborator`, `AirtableButton`,
  `Sort`/`SortDirection`, `AirtableDateParser`, `AirtableJacksonModule`.
- 2.3 `AirtableClient.java` — starts with the URL-encoding verification spike (§2.3.9).
- 2.4 `AirtableQuery.java`; 2.5 `Fields.java`; 2.6 `DictTable.java`; 2.7 `CacheStore.java`
  skeleton (API + lock; TTL/LRU population deferred to F9).
- 2.8 `AirtableJson.java` — shared mapper + coercions (§2.3.3).
- 2.9 Unit tests: TestAirtableQueryBuild, TestAirtableExceptionDecoding,
  TestFieldsDualAccess, TestDateDecoding, TestSpecialErrorDecoding, TestValueCoercion,
  TestClientUrlEncoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration test ASAP

- 3.1 `generate_java()` entry + static copy (exclude AirtableRuntime.java / Formula.java
  per flags).
- 3.2 `write_options()` — enum per select field; SCREAMING_SNAKE entries; raw-value
  mapping; dedup collisions (v2/v3 suffix parity).
- 3.3 `write_field_types()` — `{Table}Fields` final class (per-field Id/Name constants,
  idByName/nameById maps, allIds) + `{Table}View` enum.
- 3.4 `write_tables()` (dict accessor only).
- 3.5 `write_main()` — `public final class Airtable(baseId, apiKey, cacheSeconds)` with
  per-table accessor methods.
- 3.6 Offline unit tests (content assertions; no compile shell-out).
- 3.7 **Integration**: `TestStructCrudViaTable.java` green against the real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `AirtableModel.java` interface; 4.2 `OrmTable.java` incl. upsert.
- 4.3 `write_models()` — fields + getters/setters + Builder per §2.3.1; `@JsonProperty`
  field IDs; snapshot dirty tracking; Javadoc per field; evaluate methods when
  runtime=True.
- 4.4 `write_tables()` ORM accessor.
- 4.5 Unit tests `TestJavaComputedFields`: computed = no setter + not in Builder;
  writable = setter + Builder method; `@JsonProperty` IDs present; payload builders
  exclude computed; evaluate methods gated on runtime flag.
- 4.6 Offline `TestSerializing.java` (8 parity cases from the Kotlin/Swift list).
- 4.7 **Integration**: TestOrmCrudViaTable (primary-key-only, all-simple-props,
  upsert-as-create/update, 111-record batch, field selection, maxRecords, invalid-ID
  error), TestOrmCrudViaModel (save/fetch/delete paths).

### Feature 5 — Complex Field Types [P2]

- 5.1 Attachment upload (URL-based, TS parity); 5.2 collaborator encode/decode;
  5.3 computed `MaybeSpecialOrError` end-to-end decode; 5.4 button decode; 5.5 duration
  round-trip magnitude assertion.
- 5.6 **Integration**: TestComplexProperties.java + complex sections of CRUD files.
- 5.7 **Integration**: TestSpecialErrorDeser.java (parity w/ Rust/Swift/Kotlin).

### Feature 6 — Linked Records [P2]

- 6.1 Generator: raw `List<String>` record-ID fields (no wrapper).
- 6.2 **Integration**: TestLinkedRecords.java — link arrays + resolution via
  `airtable.secondary().get(ids)`.

### Feature 7 — Formula Builders [P2]

- 7.1 Field classes in Formula files (eq/neq per §2.3.2); 7.2 combinators; 7.3
  `write_formula_helpers()` → `{Table}Filters` + `static final f`.
- 7.4 Unit tests `TestFormula.java` (~86 cases mirroring Rust/Kotlin categories:
  combinators 8, id 4, text 24, single-select 4, multi-select 4, number 10, bool 4,
  date 25, attachment 3).
- 7.5 **Integration**: TestFilterByFormula.java.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler: `"java"` in Language literal; `_runtime = "AirtableRuntime"`,
  `_self = "this"`; Java arms in all ~28 guarded emitter blocks (literals,
  FieldRef → `V()`, AND/OR/NOT/XOR via `isTruthy()` + `&&`/`||`, IF via ternary,
  IFS/SWITCH, LEN/BLANK/TRUE/FALSE/RECORD_ID, \_emit_str/\_emit_num/\_emit_eq_operand/
  \_emit_binary_op/\_emit_unary_op, runtime-call fallthrough); `_java_ident` renaming.
- 8.2–8.8 `AirtableRuntime.java` groups: math 26 (incl. EXP pin §2.3.6), logic 8,
  string 14+, date 21+ (java.time), array 4, regex 4.
- 8.9 Generator wires evaluate methods on models.
- 8.10 `tests/test_formula_transpiler_java.py` (mirror Kotlin twin).
- 8.11 `TestAirtableRuntime.java` ≈180 cases (parity w/ Rust/Swift/Kotlin).
- 8.12 **Integration**: TestRuntimeFormulas.java.

### Feature 9 — Caching [P3]

- 9.1 CacheStore TTL/LRU/per-table wipe; 9.2 client cached read paths; 9.3 mutation
  invalidation; 9.4 invalidateAllCaches() + per-table invalidate.
- 9.5 **Integration**: TestCaching.java (~10 scenarios, Rust parity).

### Feature 10 — Serialization (integration portion) [P3]

- 10.1 Network-bound TestSerializing cases: linked-record ID arrays, createdTime
  round-trip, unsaved-id behavior.

### Feature 11 — Parity Audit & Polish [P3]

- 11.1 File-by-file test diff vs Kotlin/Swift/Rust/Python/TS; file follow-ups for gaps.
- 11.2 `./checks.sh` both repos green; 11.3 `./test.sh all` green (seven languages);
  11.4 `main.py all` with java alongside others; 11.5 README updates (both repos).

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

| #   | Risk                                                                                    | Mitigation                                                                          |
| --- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| R1  | Jackson generic deser for `VecOrValue<MaybeSpecialOrError<T>>` (ContextualDeserializer) | §2.3.4 pattern; F1.13 prototype gate incl. nested composition                       |
| R2  | Package-vs-directory mismatch breaks javac/Gradle                                       | §2.3.5 verify-first compile proof in F1.13; fallback directory layout               |
| R3  | Computed-field decode vs create-payload exclusion                                       | §2.3.1 field-access + no-setter design + hand-rolled payload builders               |
| R4  | Java keyword collision (no escape mechanism)                                            | `_java_ident()` `_`-suffix rename + unit tests incl. `_` and literals               |
| R5  | URL encoding (`+`, spaces, path vs query)                                               | §2.3.9 verify-first spike; TestClientUrlEncoding; formula round-trip test           |
| R6  | `Math.exp(1.0)` ULP mismatch vs Airtable                                                | Port Kotlin's EXP pin verbatim; runtime parity tests catch regressions              |
| R7  | google-java-format missing / fights generated style                                     | `command -v` guards both repos; never format generated output                       |
| R8  | Builder + setters + getters balloon generated LOC                                       | Accept (idiomatic Java is verbose); offline content tests keep templates honest     |
| R9  | JUnit cross-class parallelism racing shared records                                     | Parallelism off; distinct primary keys per file                                     |
| R10 | Jackson version churn / module registration mistakes                                    | Exact pins in F1; shared mapper is the ONLY mapper (no ad-hoc `new ObjectMapper()`) |
| R11 | Transpiler emits invalid Java for edge formulas                                         | test_formula_transpiler_java.py + TestRuntimeFormulas integration                   |
| R12 | Gradle cold-start slowness in test.sh                                                   | Daemon + configuration cache on (same as Kotlin)                                    |
| R13 | Disambiguated lookup/rollup fields skip Java types                                      | F1.3 explicit `apply_disambiguated_type` task + unit test                           |
| R14 | Boxed `Double` equality surprises in tests                                              | Tests use `assertEquals(42.0, x)` with Double; document Airtable-numbers-are-Double |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py java <folder>` generates a compiling Java source set.
- [ ] `uv run main.py all --java-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Java included.
- [ ] `./test.sh all` (myairtable-tests) green with Java included (seven languages).
- [ ] All ten integration test files green (struct/orm crud ×3, serializing, filter,
      runtime, caching, linked, complex, special-deser).
- [ ] Formula builder + runtime unit-test counts within ±5% of Rust/Kotlin.
- [ ] Upsert + dual ID/name Fields access tested.
- [ ] Generated code is idiomatic Java 21 (records/sealed for sums, builders, unchecked
      exceptions, no Kotlin-isms).
