# Java Language Support — Implementation Plan v2

> **Changes from v1 (plan-critic round, 2026-06-12)**: specified the Jackson instantiation
> contract — every generated model emits a public no-arg constructor (CRIT-2); moved
> `@JsonDeserialize` registration from the sealed interfaces to **field-level annotations
> emitted by the generator** (CRIT-3); enumerated the transpiler integration precisely —
> `Language` literal at formula_transpiler.py:21, `_runtime` initializer at :326 must add
> `"java"`, bare `S()`/`N()` Kotlin arms in `_emit_str`/`_emit_num` become qualified
> `AirtableRuntime.S()`/`AirtableRuntime.N()` for Java, evaluate methods return Jackson
> `JsonNode` with explicit node-constructor mapping (CRIT-4, HIGH-9, HIGH-10); explicitly
> tasked the `map_types()` first-pass line AND `apply_disambiguated_type()` java line
> (HIGH-7); expanded `AirtableModel.java` to full Kotlin parity — `attachedClient`,
> `toCreateFields()`, `requireId()`, with per-model fluent `save()`/`fetch()`/`delete()`
> emitted by the generator (HIGH-8); added `TestDxHelpers.java` (16th unit-test file) and
> the DX helper APIs it covers (HIGH-5); added `AirtableView.java` + `withView` (MED-12);
> mandated Builder for integration-test creation (MED-13); corrected the URLEncoder-vs-Ktor
> equivalence claim (MED-15); consolidated ALL coercion helpers onto `AirtableRuntime`
> (MED-16); added the `jackson-datatype-jsr310` Duration-shadowing risk (LOW-20);
> `make_test_base` fix now also adds the missing `_swift_type`/`_rust_type` keys (CRIT-1).

## 1. Overview & Goals

Add full-parity **Java** code generation to `myairtable` — the seventh target, alongside
Python, TypeScript, JavaScript, Rust, Swift, and Kotlin. The closest template is the Kotlin
target (completed 2026-06-12, epic `myairtable-kxrj`): same JVM, same Gradle/JDK-21
infrastructure, same test-base semantics. But the generated code must feel **idiomatic
Java 21** — not Kotlin-with-semicolons: JavaBeans accessors, generated builders, sealed
interfaces + records + pattern-matching switch for sum types, unchecked exception
hierarchy, plain blocking methods (virtual-thread friendly), Jackson for JSON.

**Scope:**

- Generator at `src/generators/java.py` + `src/utils/write_to_java_file.py`
- Static runtime at `static/java/` (custom Airtable client — JDK HttpClient + Jackson; no
  third-party Airtable SDK)
- Type mapping (`GENERIC_TO_JAVA`) + formula transpiler Java emitter
- Unit tests: `tests/test_generators.py` Java classes, `tests/test_formula_transpiler_java.py`,
  `tests/java_static/` Gradle test project (16 test files, Kotlin parity)
- Integration tests at `myairtable-tests/java/` (parity with Kotlin/Swift/Rust/TS)
- CLI wiring (`main.py java` + `all --java-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`

**Non-goals (v1):** Maven publishing / POM emission; CompletableFuture async variants;
module-info.java (JPMS); annotation processors (Lombok etc. — generator writes everything
explicitly); `jackson-datatype-jsr310` (deliberately excluded, §2.3.6).

## 2. Design Decisions

### 2.1 User-approved (2026-06-12)

| #   | Question     | Answer                                                   |
| --- | ------------ | -------------------------------------------------------- |
| 1   | Java version | **Java 21 LTS** (toolchain 21, same as Kotlin)           |
| 2   | Build tool   | **Gradle** (committed wrapper, foojay resolver, JUnit 5) |
| 3   | HTTP + JSON  | **JDK `java.net.http.HttpClient` + Jackson databind**    |
| 4   | API style    | **Synchronous blocking** (virtual-thread friendly)       |

### 2.2 Kotlin-pattern → Java idiom mapping

| Kotlin construct                                   | Java equivalent                                                                                                                                                                       |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `class AirtableClient` + Ktor + coroutines `Mutex` | `final class AirtableClient` + `java.net.http.HttpClient` + `ReentrantLock`                                                                                                           |
| `@Serializable` class, `@SerialName` = field ID    | Mutable POJO + Jackson `@JsonProperty` (field-ID raw values), field-access mode, **public no-arg constructor** (§2.3.1)                                                               |
| kotlinx `JsonElement`                              | Jackson `JsonNode` (type-erased formula/runtime value)                                                                                                                                |
| `sealed interface VecOrValue<T>` + KSerializer     | `sealed interface VecOrValue<T>` w/ nested records `Single`/`Multiple` + custom `JsonDeserializer` (`ContextualDeserializer`), **annotated at the field, not the interface** (§2.3.4) |
| `sealed interface MaybeSpecialOrError<T>`          | Same pattern: nested records `Value<T>` / `Special<T>` / `Error<T>`                                                                                                                   |
| Select-option `enum class` + `@SerialName`         | `enum` with raw-value field + `@JsonValue` (encode) / `@JsonCreator` (decode)                                                                                                         |
| `sealed class AirtableException : Exception`       | `sealed abstract class AirtableException extends RuntimeException permits …` (**unchecked**, §2.3.7)                                                                                  |
| `suspend fun`                                      | Plain blocking method (callers may wrap in virtual threads)                                                                                                                           |
| `object AirtableRuntime` + top-level `V/N/S/…`     | `public final class AirtableRuntime` — static methods, private ctor; **owns ALL coercion helpers** (§2.3.3)                                                                           |
| `companion object { val f }` filter accessor       | `public static final PrimaryFilters f = new PrimaryFilters();` → `PrimaryModel.f.primaryKey.eq(...)`                                                                                  |
| Backtick keyword escaping                          | **No escape mechanism in Java** — `_java_ident()` renames reserved words with `_` suffix (`class` → `class_`); set includes all keywords + literals `true`/`false`/`null` + `_`       |
| `typealias RecordId = String`                      | Plain `String` (no typealias in Java); `RecordId` appears only in Javadoc                                                                                                             |
| `java.time.Instant` + AirtableInstantSerializer    | Same `Instant`; custom Jackson (de)serializer in `AirtableJacksonModule` (3-format)                                                                                                   |
| `kotlin.time.Duration` (wire = seconds)            | `java.time.Duration`; custom (de)serializer, wire = **numeric seconds** (§2.3.6)                                                                                                      |
| Named/default args for creation                    | **Generated nested `Builder`** (writable fields only) — mandated creation idiom in tests (§2.3.11)                                                                                    |
| reified `save()`/`fetch()`/`delete()` extensions   | **Generator-emitted per-model fluent methods** with covariant return (§2.3.12)                                                                                                        |
| `interface AirtableView { val id }` + `withView`   | `interface AirtableView { String getId(); }`; `{Table}View` enums implement it                                                                                                        |

### 2.3 Java-specific decisions

#### 2.3.1 Model shape: mutable POJO + no-arg ctor + getters/setters + Builder (CRIT-2)

```java
public final class PrimaryModel implements AirtableModel {
    /** Single Line Text {@code fldXXX} */
    @JsonProperty("fldXXX")
    private String singleLineText;                       // writable: getter + setter

    /** Auto Number {@code fldYYY} — read-only */
    @JsonProperty("fldYYY")
    @JsonDeserialize(using = MaybeSpecialOrErrorDeserializer.class)
    private MaybeSpecialOrError<Long> autoNumber;        // computed: getter ONLY

    public PrimaryModel() {}                             // REQUIRED: Jackson creator

    public String getSingleLineText() { ... }
    public void setSingleLineText(String v) { ... }
    public MaybeSpecialOrError<Long> getAutoNumber() { ... }

    public static Builder builder() { ... }
    public static final class Builder { /* writable-field methods only + build() */ }
}
```

- **Jackson instantiation contract**: Jackson instantiates via the **public no-arg
  constructor** and injects private fields directly (mapper configured
  `PropertyAccessor.FIELD = ANY`, getters/setters/creators `NONE`). Every generated model
  MUST emit `public {Table}Model() {}`. No all-args constructor is generated (nothing for
  Jackson to misroute to). `Builder.build()` constructs via the no-arg ctor + setters.
  Proven by the F1.13 prototype gate before any templating.
- `@JsonProperty` lives once, on the field; raw values are **field IDs**.
- Computed fields are decode-only by construction: Jackson sets the private field; no
  setter exists, and Builder omits them.
- Create/update payloads are **hand-rolled** (`toCreateFields()` / `dirtyFields()`
  returning `Map<String, JsonNode>` over writable field IDs only) — port of Kotlin §2.3.1.
  The mapper is used wholesale only for **decoding**.
- Dirty tracking: `@JsonIgnore private Map<String, JsonNode> snapshot` + diff.
- Boolean getter naming: uniform `getX()` (fields are boxed `Boolean`; `isX()` is the
  primitive-`boolean` convention).

#### 2.3.2 Filter DSL keeps `eq` / `neq`

Java has the same footgun as Kotlin (CRIT-3 there): `equals(Object)` exists on every
class, so a generated `equals(String)` overload silently binds to `Object.equals`
(returning `boolean`, not `Formula`) for non-String arguments. Keep `eq`/`neq`; all other
names match the other languages (`contains`, `startsWith`, `greaterThan`, `isEmpty`/
`isNotEmpty`, …). Also gives cross-JVM consistency with Kotlin.

#### 2.3.3 `JsonNode` is the type-erased value; ALL coercions live on `AirtableRuntime` (MED-16)

The formula runtime operates on `JsonNode`. Unlike Kotlin (top-level functions in
`AirtableJson.kt`, emitted bare), Java has no top-level functions: **every coercion
helper — `V`, `N`, `S`, `A`, `AN`, `AS`, `D`, `isTruthy` — is a static method on
`AirtableRuntime`**, so the transpiler's single `_runtime = "AirtableRuntime"` qualifier
covers all of them. `AirtableJson.java` owns ONLY the shared `ObjectMapper` singleton and
module registration. No reification needed:

```java
public static JsonNode V(Object value) {
    return value == null ? NullNode.getInstance() : AirtableJson.MAPPER.valueToTree(value);
}
```

`valueToTree` dispatches on runtime type; the shared mapper (with Instant/Duration
serializers registered) handles every field type, including `Instant`/`Duration` inside
`V()`.

#### 2.3.4 Generic deserializers: `readTree` peek + `ContextualDeserializer`, registered AT THE FIELD (CRIT-3)

Jackson's analog of Kotlin's `decodeJsonElement()` peek: a `JsonDeserializer` that reads
the subtree as `JsonNode`, dispatches structurally, then converts the payload using the
element type captured in `createContextual()` (Jackson's mechanism for generics — the
`BeanProperty`'s declared field type carries the concrete generic arguments):

- `VecOrValue<T>`: `node.isArray()` → `Multiple(List<T>)`, else → `Single(T)`
- `MaybeSpecialOrError<T>`: object with `"specialValue"` → `Special`; object with
  `"error"` → `Error`; else convert to `T` → `Value`

**Registration is field-level, NOT interface-level**: `@JsonDeserialize(using = …)` on a
generic sealed interface is unreliable for varying generic instantiations. Instead, **the
generator emits `@JsonDeserialize(using = VecOrValueDeserializer.class)` (or
`MaybeSpecialOrErrorDeserializer.class`) on every model field whose mapped type uses those
wrappers** — mechanical, since `apply_java_computed_wrapping()` already knows. Inner
`MaybeSpecialOrError` inside `VecOrValue<MaybeSpecialOrError<T>>` is handled by the outer
deserializer delegating through the contextual type (two-level chaining). Encoding uses
matching `JsonSerializer`s (or `@JsonValue`-style unwrap) — encode parity is required for
`toRecord()` round-trips. JSON-format-only is acceptable.

**F1.13 prototype gate**: round-trips for `MaybeSpecialOrError<String>`, `<Double>`,
`<Instant>`, `VecOrValue<String>`, and the nested `VecOrValue<MaybeSpecialOrError<String>>`
with field-level annotations on a real POJO — decode AND encode.

#### 2.3.5 Flat package `myairtable`; one public type per file

All files (static + generated) declare `package myairtable;`. **Verify-first gate**: javac
requires `public class X` in `X.java`, but package-vs-directory mismatch is fine when
Gradle passes explicit source lists (it disables sourcepath). F1.13 proves
`output/dynamic/models/PrimaryModel.java` with `package myairtable;` compiles under
`sourceSets.main.java.srcDir("output")`. Fallback if it fails: emit everything under a
`myairtable/` directory root.

Kotlin's multi-type files (Types.kt: 14 top-level types) split one-file-per-public-type;
closely-coupled small types nest (records `Single`/`Multiple` inside `VecOrValue`;
`Thumbnail` inside `AirtableThumbnails`; exception subclasses nested in
`AirtableException`).

#### 2.3.6 Date / Duration / numbers (incl. LOW-20)

- `AirtableDateParser` port: `Instant.parse()` → `OffsetDateTime.parse().toInstant()` →
  `LocalDate.parse().atStartOfDay(ZoneOffset.UTC).toInstant()`. Registered via
  `AirtableJacksonModule` on the shared mapper.
- Duration wire unit: **numeric seconds** (locked by Swift/Kotlin live verification).
  **Risk (Kotlin had the exact analog)**: `jackson-datatype-jsr310`'s `JavaTimeModule`
  would shadow the custom Duration serializer with ISO-8601 (`"PT30S"`). Mitigation: do
  NOT depend on jsr310; never call `findAndRegisterModules()`; register only
  `AirtableJacksonModule`. F1.13 asserts Duration encodes as a number, not `"PT30S"`.
- Airtable `number` fields are ALWAYS `Double` (never `Long`) — tests use `42.0`.
  `autoNumber`/`count` map to `Long` (matches `GENERIC_TO_KOTLIN`).
- **JVM `Math.exp(1.0)` is one ULP above V8's `Math.E`** — port Kotlin's pinned
  `EXP(1.0) == Math.E` special case verbatim (same JVM, same bug).

#### 2.3.7 Errors: unchecked sealed hierarchy

`public sealed abstract class AirtableException extends RuntimeException` with nested
final subclasses `Http(status, body)`, `Api(code, message)`, `Decoding(cause)`,
`InvalidUrl`, `MissingCredentials`, `RateLimited(retryAfterSeconds)`. Unchecked because
checked exceptions would poison every generated signature — modern Java library idiom.
Pattern-matching `switch` over the hierarchy works in tests.

#### 2.3.8 Concurrency

Plain blocking client. `CacheStore` guards its maps with `ReentrantLock`; JDK
`HttpClient` is thread-safe and shared. 429 retry/backoff uses `Thread.sleep` (fine on
virtual threads; `InterruptedException` wrapped into `AirtableException`). No executor
ownership; callers control threading.

#### 2.3.9 URL encoding verify-first (corrected per MED-15)

`URLEncoder.encode(v, UTF_8)` is **form encoding**: `+` → `%2B`, space → `+`. This is
NOT what Ktor did by default — Ktor originally left `+` raw (the Kotlin/Swift bug) and
the working behavior is `+` arriving as `%2B`. So `URLEncoder`'s default is _likely
already correct_ for query values — but that's an inference, not a verification. The
**verify-first spike** must confirm: `URLEncoder.encode("LEN({field})+1")` →
`LEN%28%7Bfield%7D%29%2B1`, Airtable accepts it un-double-decoded, and a `LEN({f})+1`
filter formula round-trips against the real base. **Path segments are different**: table
names in the URL path need RFC-3986 (`%20` for spaces, literal `+` allowed) — use
`URI`-based path encoding, never `URLEncoder`, for path segments. Both pinned by
`TestClientUrlEncoding.java`.

#### 2.3.10 Formatter & lint

`google-java-format` (brew-installable) with `command -v` warn-skip guards in BOTH repos'
checks.sh — exact ktlint pattern. Scope: `static/java/`, `tests/java_static/src/`,
`myairtable-tests/java/src/` — NEVER generated output. Generator emits near-google-style
output so runtime files stay stable under formatting.

#### 2.3.11 Creation idiom: Builder is mandated (MED-13)

Generated `Builder` (writable fields only) is THE creation idiom; integration tests use
`PrimaryModel.builder().primaryKey("x").build()` everywhere (the Java analog of Kotlin's
`PrimaryModel(primaryKey = "x")`). Plain setters are for post-fetch mutation
(`model.setEmail(...)` before `save()`). No separate Create class (cross-language
decision stands — Builder is a construction helper for the same model type, not a second
model type).

#### 2.3.12 Model DX surface: `AirtableModel` parity + per-model fluent methods (HIGH-8, HIGH-5)

Kotlin's `AirtableModel` carries `attachedClient` and reified extensions
`save()`/`fetch()`/`delete()` plus `requireId()`/`requireAttachedClient()` — exercised by
`TestOrmCrudViaModel` and `TestDxHelpers`. Java equivalents:

- `AirtableModel.java` interface: `getId()`/`setId()`, `getCreatedTime()`/
  `setCreatedTime()`, `getAttachedClient()`/`setAttachedClient()`, `takeSnapshot()`,
  `dirtyFields()`, `toRecord()`, `toCreateFields()`, `isNew()`; **default methods**
  `requireId()` and `requireAttachedClient()` (throw `AirtableException.Api("UNSAVED_MODEL", …)`
  / missing-client respectively).
- Java has no reified generics, so fluent CRUD is **generator-emitted per model** with
  covariant returns, delegating to a static helper:
  `public PrimaryModel save() { return ModelOps.save(this, PrimaryModel.class); }`
  (likewise `fetch()`, `delete()`). `ModelOps.java` (static; uses `attachedClient`,
  the model's table id, and the class token for decode) joins the static runtime.
- DX value accessors (Kotlin's `.value` / `.cleanValues`): `default T value()` on
  `MaybeSpecialOrError<T>` (null unless `Value`); `values()` / `cleanValues()` helpers
  for `VecOrValue<T>` / `VecOrValue<MaybeSpecialOrError<T>>` (default methods where
  generics allow, static helpers on the interface otherwise). Covered by
  `TestDxHelpers.java`.

### 2.4 Other settled choices

| Decision            | Value                                                                                                                                                                       |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Test framework      | JUnit 5 (`org.junit.jupiter`), `Assertions.*`                                                                                                                               |
| Integration phasing | `@TestInstance(PER_CLASS)` + `@TestMethodOrder(OrderAnnotation)`; shared fields for IDs                                                                                     |
| Test parallelism    | Cross-class parallelism OFF; distinct primary keys per file (`"Java StructCrud PKOnly {ts}"`)                                                                               |
| File naming         | `PascalCase.java` (forced: public type = filename); properties `lowerCamelCase` via `name_camel()`                                                                          |
| Select-option enums | Constants SCREAMING_SNAKE_CASE via `_choice_to_entry()` port; raw value via `@JsonValue` field + `@JsonCreator` factory; dedup collisions (v2/v3 suffix parity with Kotlin) |
| Linked records      | Raw `List<String>` record IDs; resolve via `airtable.secondary().get(ids)`                                                                                                  |
| Dirty tracking      | `@JsonIgnore` snapshot map + diff (port of Kotlin/Swift/Rust)                                                                                                               |
| Table accessors     | `airtable.primary()` methods (no top-level `val` in Java)                                                                                                                   |
| build.gradle.kts    | NOT emitted by generator — hand-written in consuming projects                                                                                                               |
| Gradle wrapper      | Committed in both `tests/java_static/` and `myairtable-tests/java/` (same Gradle as Kotlin)                                                                                 |
| Javadoc             | `/** … */`, `{@code …}` for field IDs, formula text in `<pre>{@code …}</pre>` (escape `*/`, `@`, `{`/`}` carefully — unit-tested)                                           |

## 3. File Layout

### 3.1 Source repo (`myairtable`)

```
src/generators/java.py                # NEW ~1100 LOC (mirrors kotlin.py structure)
src/utils/write_to_java_file.py       # NEW WriteToJavaFile (Javadoc, region comments, class/enum/
                                      #   method/field helpers, _java_ident() underscore-suffix
                                      #   rename incl. literals + `_`, _choice_to_entry(),
                                      #   _java_string_literal())
src/utils/type_mapper.py              # MOD: GENERIC_TO_JAVA; "java" in Language literal (:321);
                                      #   LanguageConfig entry (list_fmt="List<{0}>",
                                      #   union_fmt="VecOrValue<{0}>"); map_java_type();
                                      #   apply_java_computed_wrapping(); is_already_list java
                                      #   case; **map_types() first-pass java line (≈:202-209
                                      #   kotlin analog)**; **apply_disambiguated_type() java
                                      #   branch (≈:806-813)** — both call
                                      #   apply_java_computed_wrapping
src/utils/write_to_file.py            # MOD: "java" in language Literal (:49) + header match case
src/meta.py                           # MOD: _java_type PrivateAttr + java_type property
src/formulas/formula_transpiler.py    # MOD (enumerated): "java" in Language literal (:21);
                                      #   _self — java falls into existing else → "this" (:323, no
                                      #   change but covered by test); _runtime — ADD java to the
                                      #   ("swift","kotlin") branch → "AirtableRuntime" (:326);
                                      #   java arms in ALL kotlin-guarded blocks (~28): literals
                                      #   (NullNode.getInstance() / TextNode.valueOf / DoubleNode.
                                      #   valueOf / BooleanNode.getTrue|getFalse), FieldRef →
                                      #   AirtableRuntime.V(this.x) (QUALIFIED — Kotlin emits bare
                                      #   V()), AND/OR/NOT/XOR via AirtableRuntime.isTruthy(...) +
                                      #   &&/||/!, IF via ternary, IFS/SWITCH, LEN/BLANK/TRUE/
                                      #   FALSE/RECORD_ID, **_emit_str (:1083-1086) and _emit_num
                                      #   (:1107-1110): bare S()/N() kotlin arms get java arms
                                      #   emitting AirtableRuntime.S()/AirtableRuntime.N()**,
                                      #   _emit_eq_operand/_emit_binary_op/_emit_unary_op,
                                      #   runtime-call fallthrough; _java_ident renaming
main.py                               # MOD: `java` command + `all --java-folder`
checks.sh                             # MOD: java section (google-java-format guard +
                                      #   ./gradlew test in tests/java_static; warn-skip w/o JVM)
static/java/                          # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestJava* classes; make_test_base
                                      #   __pydantic_private__ gains "_java_type": None AND the
                                      #   missing "_swift_type": None / "_rust_type": None
                                      #   (pre-existing gap — audit all language keys)
tests/test_formula_transpiler_java.py # NEW (mirror Kotlin twin)
tests/java_static/                    # NEW Gradle project (wrapper committed)
  ├── settings.gradle.kts / build.gradle.kts / gradlew / gradle/wrapper/
  └── src/
      ├── main: sourceSets srcDir → ../../static/java
      └── test/java/myairtable/          # 16 files = Kotlin parity
          ├── TestPojoModel.java         # F1.13 prototype gate (§2.3.1/2.3.4/2.3.5/2.3.6)
          ├── TestHarness.java
          ├── TestAirtableQueryBuild.java
          ├── TestAirtableExceptionDecoding.java
          ├── TestCacheStore.java
          ├── TestClientCachePolicy.java
          ├── TestClientHardening.java
          ├── TestClientUrlEncoding.java
          ├── TestDateDecoding.java
          ├── TestDxHelpers.java         # requireId, value()/cleanValues(), withView
          ├── TestSpecialErrorDecoding.java
          ├── TestFieldsDualAccess.java
          ├── TestValueCoercion.java
          ├── TestTableBoundedOps.java
          ├── TestFormula.java           # ~86 builder cases
          └── TestAirtableRuntime.java   # ≈180 runtime cases
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
├── build.gradle.kts               # HAND-WRITTEN: java plugin, toolchain 21, Jackson + JUnit 5
│                                  #   deps (NO jackson-datatype-jsr310, §2.3.6),
│                                  #   sourceSets.main.java.srcDir("output")
├── gradle.properties              # configuration-cache + caching on
├── gradlew / gradle/wrapper/      # committed
├── output/                        # regenerated by build.sh
└── src/test/java/myairtable/tests/
    ├── TestHarness.java           # smoke: MyAirtableRuntimeInfo.VERSION reachable
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
test.sh                            # MOD: java case + ADD java to `for lang in ts js py rs swift kotlin`
checks.sh                          # MOD: google-java-format (command -v guard) +
                                   #      (cd java && ./gradlew compileTestJava)
```

`test.sh` java case (Gradle `--tests` wildcards match simple class names for Java exactly
as for Kotlin):

```bash
elif [ "$LANG_ARG" = "java" ]; then
    case "$SUITE" in
        --all)     TEST_CMD="(cd java && ./gradlew test)" ;;
        --crud)    TEST_CMD="(cd java && ./gradlew test --tests '*TestStructCrudViaTable' --tests '*TestOrmCrudViaTable' --tests '*TestOrmCrudViaModel')" ;;
        --json)    TEST_CMD="(cd java && ./gradlew test --tests '*TestSerializing')" ;;
        --filter)  TEST_CMD="(cd java && ./gradlew test --tests '*TestFilterByFormula')" ;;
        --runtime) TEST_CMD="(cd java && ./gradlew test --tests '*TestRuntimeFormulas')" ;;
        --cache)   TEST_CMD="(cd java && ./gradlew test --tests '*TestCaching')" ;;
    esac
```

## 4. Static Runtime Contract (static/java/, ~27 files, ~4,500 LOC)

One public type per file (Java requirement). Nested types noted inline.

| File                                                | Contents                                                                                                                                                                                    |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AirtableException.java`                            | sealed abstract base + nested finals: Http, Api, Decoding, InvalidUrl, MissingCredentials, RateLimited(retryAfterSeconds) — unchecked (§2.3.7)                                              |
| `AirtableClient.java`                               | JDK HttpClient, bearer auth, 429 retry/backoff, all record endpoints, owns CacheStore, chunk-of-10 batching; path-vs-query encoding (§2.3.9 verify-first)                                   |
| `AirtableJson.java`                                 | Shared `ObjectMapper` singleton ONLY (fail-on-unknown OFF, field access, NON_NULL, AirtableJacksonModule registered; never `findAndRegisterModules()`)                                      |
| `AirtableJacksonModule.java`                        | Module registering Instant (3-format) + Duration (numeric seconds) (de)serializers                                                                                                          |
| `AirtableDateParser.java`                           | 3-format parse port                                                                                                                                                                         |
| `CacheStore.java`                                   | TTL + LRU behind ReentrantLock; per-table wipe; invalidateAll()                                                                                                                             |
| `AirtableModel.java`                                | interface per §2.3.12: id/createdTime/attachedClient accessors, takeSnapshot(), dirtyFields(), toRecord(), toCreateFields(), isNew(); default requireId()/requireAttachedClient()           |
| `ModelOps.java`                                     | static save/fetch/delete helpers backing the generated per-model fluent methods (§2.3.12)                                                                                                   |
| `AirtableQuery.java`                                | formula, sort, fields, maxRecords, pageSize, view, returnFieldsByFieldId; toParameters(); `withView(AirtableView)`                                                                          |
| `AirtableView.java`                                 | `interface AirtableView { String getId(); }` — implemented by generated `{Table}View` enums                                                                                                 |
| `Fields.java`                                       | Wraps `Map<String, JsonNode>`; dual ID/name get/set (ID-first, name fallback)                                                                                                               |
| `DictTable.java`                                    | Raw CRUD returning Fields; mirrors OrmTable API                                                                                                                                             |
| `OrmTable.java`                                     | `OrmTable<T extends AirtableModel>` — typed CRUD + upsert(model, matchFields), batching, cache invalidation                                                                                 |
| `Formula.java` + field classes                      | `Formulas` combinators (and/or/not/xor) + Text/Number/Date/Boolean/Select/MultiSelect/Link/Id/Attachment field classes using eq/neq — split into separate files as one-public-type requires |
| `AirtableRuntime.java`                              | final class, static — ALL coercions V/N/S/A/AN/AS/D/isTruthy (§2.3.3) + ~80 formula functions (math incl. EXP pin, logic, string, date via java.time, array, regex)                         |
| `VecOrValue.java`                                   | sealed interface + nested records Single/Multiple + value accessors; deserializer in own file                                                                                               |
| `VecOrValueDeserializer.java`                       | ContextualDeserializer (§2.3.4) + matching serializer                                                                                                                                       |
| `MaybeSpecialOrError.java`                          | sealed interface + nested records Value/Special/Error + `default T value()`                                                                                                                 |
| `MaybeSpecialOrErrorDeserializer.java`              | ContextualDeserializer + matching serializer                                                                                                                                                |
| `SpecialNumber.java` / `ErrorValue.java`            | records (`{"specialValue": …}` / `{"error": …}`)                                                                                                                                            |
| `AirtableRecord.java`                               | generic record envelope (id, createdTime, fields)                                                                                                                                           |
| `AirtableAttachment.java`                           | + nested Thumbnails/Thumbnail                                                                                                                                                               |
| `AirtableCollaborator.java` / `AirtableButton.java` | data carriers                                                                                                                                                                               |
| `Sort.java` / `SortDirection.java`                  | sort spec + enum                                                                                                                                                                            |
| `MyAirtableRuntimeInfo.java`                        | VERSION constant                                                                                                                                                                            |

## 5. Feature Breakdown (→ beads epic/features/tasks)

### Feature 1 — Scaffolding & Infrastructure [P0]

- 1.1 `"java"` in `WriteToFile.language` literal (write_to_file.py:49) + header match case.
- 1.2 `write_to_java_file.py` (`WriteToJavaFile` + reserved-word set incl. literals +
  `_` + `_java_ident()` `_`-suffix rename + `_choice_to_entry()` + `_java_string_literal()`
  - Javadoc escaping).
- 1.3 Type system wiring — ALL of: `GENERIC_TO_JAVA`; `"java"` in type_mapper `Language`
  literal; `LanguageConfig` entry; `map_java_type()`; `apply_java_computed_wrapping()`;
  `is_already_list` java case; **`map_types()` first-pass java line**;
  **`apply_disambiguated_type()` java branch** (both apply computed wrapping); meta.py
  `_java_type` PrivateAttr + property; `make_test_base` `__pydantic_private__` gains
  `"_java_type": None` **plus the missing `"_swift_type": None` / `"_rust_type": None`**
  (audit completeness for all languages).
- 1.4 `main.py java` command (flags: formulas, wrappers, runtime, flatten).
- 1.5 Wire into `main.py all()` (`--java-folder`).
- 1.6 `tests/java_static/` Gradle project (wrapper committed; java plugin; toolchain 21 +
  foojay; Jackson databind + JUnit 5 exact pins; NO jsr310).
- 1.7 `myairtable-tests/java/` Gradle skeleton (hand-written build files + wrapper;
  `output/` srcDir).
- 1.8 `myairtable-tests/build.sh`: `--java-folder`.
- 1.9 `myairtable-tests/test.sh`: java case (§3.3) AND add `java` to the `all` loop.
- 1.10 `myairtable-tests/checks.sh`: google-java-format `command -v` guard +
  compileTestJava.
- 1.11 `myairtable/checks.sh`: java section (format guard + `./gradlew test` in
  tests/java_static; warn-skip if no JVM).
- 1.12 `brew install google-java-format`.
- 1.13 **Prototype gate** `TestPojoModel.java` proving ALL risky foundations before any
  templating: (a) no-arg ctor + field-access decode of `@JsonProperty` field-ID keys incl.
  computed (no-setter) fields; (b) field-level `@JsonDeserialize` ContextualDeserializer
  round-trips — `MaybeSpecialOrError<String>`, `<Double>`, `<Instant>`,
  `VecOrValue<String>`, nested `VecOrValue<MaybeSpecialOrError<String>>` — decode AND
  encode; (c) Duration encodes as numeric seconds (not `"PT30S"`); (d) `@JsonIgnore`
  snapshot + writable-only payload builders; (e) package-vs-directory compile proof
  (§2.3.5).

**Exit**: `uv run main.py java <folder>` exits 0 (stub ok); both Gradle projects compile;
prototype green; both checks.sh and test.sh run their java sections without error.

### Feature 2 — Static Runtime Core [P1]

- 2.1 `AirtableException.java` hierarchy.
- 2.2 Types: `VecOrValue` (+Deserializer), `MaybeSpecialOrError` (+Deserializer),
  `SpecialNumber`, `ErrorValue`, `AirtableRecord`, `AirtableAttachment`,
  `AirtableCollaborator`, `AirtableButton`, `Sort`/`SortDirection`, `AirtableView`,
  `AirtableDateParser`, `AirtableJacksonModule`.
- 2.3 `AirtableClient.java` — starts with the URL-encoding verification spike (§2.3.9).
- 2.4 `AirtableQuery.java` incl. `withView`; 2.5 `Fields.java`; 2.6 `DictTable.java`;
  2.7 `CacheStore.java` skeleton (API + lock; TTL/LRU population deferred to F9).
- 2.8 `AirtableJson.java` (mapper only) + `AirtableRuntime` coercion statics (§2.3.3).
- 2.9 Unit tests: TestAirtableQueryBuild, TestAirtableExceptionDecoding,
  TestFieldsDualAccess, TestDateDecoding, TestSpecialErrorDecoding, TestValueCoercion,
  TestClientUrlEncoding.

### Feature 3 — Minimal Generator (dict-only) [P1] — first integration test ASAP

- 3.1 `generate_java()` entry + static copy (exclude AirtableRuntime.java / Formula files
  per flags).
- 3.2 `write_options()` — enum per select field; SCREAMING_SNAKE entries; `@JsonValue` +
  `@JsonCreator`; dedup collisions (v2/v3 suffix parity).
- 3.3 `write_field_types()` — `{Table}Fields` final class (per-field Id/Name constants,
  idByName/nameById maps, allIds) + `{Table}View` enum implementing `AirtableView`.
- 3.4 `write_tables()` (dict accessor only).
- 3.5 `write_main()` — `public final class Airtable(baseId, apiKey, cacheSeconds)` with
  per-table accessor methods.
- 3.6 Offline unit tests (content assertions; no compile shell-out).
- 3.7 **Integration**: `TestStructCrudViaTable.java` green against the real base.

### Feature 4 — ORM Models + Offline Serialization [P1]

- 4.1 `AirtableModel.java` interface (§2.3.12) + `ModelOps.java`; 4.2 `OrmTable.java`
  incl. upsert.
- 4.3 `write_models()` — no-arg ctor + fields + getters/setters + Builder per §2.3.1;
  `@JsonProperty` field IDs; field-level `@JsonDeserialize` for wrapper types (§2.3.4);
  snapshot dirty tracking; per-model `save()`/`fetch()`/`delete()`; Javadoc per field;
  evaluate methods when runtime=True.
- 4.4 `write_tables()` ORM accessor.
- 4.5 Unit tests `TestJavaComputedFields`: computed = no setter + not in Builder;
  writable = setter + Builder method; `@JsonProperty` IDs + `@JsonDeserialize` wrappers
  present; payload builders exclude computed; evaluate methods gated on runtime flag.
- 4.6 Offline `TestSerializing.java` (8 parity cases from the Kotlin/Swift list).
- 4.7 **Integration**: TestOrmCrudViaTable (primary-key-only, all-simple-props,
  upsert-as-create/update, 111-record batch, field selection, maxRecords, invalid-ID
  error), TestOrmCrudViaModel (save/fetch/delete fluent paths).

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

- 7.1 Field classes (eq/neq per §2.3.2); 7.2 combinators; 7.3 `write_formula_helpers()`
  → `{Table}Filters` + `public static final f` on models.
- 7.4 Unit tests `TestFormula.java` (~86 cases mirroring Rust/Kotlin categories:
  combinators 8, id 4, text 24, single-select 4, multi-select 4, number 10, bool 4,
  date 25, attachment 3).
- 7.5 **Integration**: TestFilterByFormula.java.

### Feature 8 — Formula Runtime Transpilation [P2]

- 8.1 Transpiler wiring exactly as enumerated in §3.1: Language literal (:21), `_runtime`
  initializer (:326), java arms in ALL ~28 kotlin-guarded blocks with Jackson node
  constructors, **qualified** `AirtableRuntime.V/S/N` (incl. `_emit_str`/`_emit_num`),
  `_java_ident` renaming. Evaluate methods return `JsonNode`.
- 8.2–8.8 `AirtableRuntime.java` groups: math 26 (incl. EXP pin §2.3.6), logic 8,
  string 14+, date 21+ (java.time), array 4, regex 4.
- 8.9 Generator wires evaluate methods on models (return `JsonNode`).
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

- 11.1 File-by-file test diff vs Kotlin/Swift/Rust/Python/TS; file follow-ups for gaps
  (incl. TestDxHelpers vs Kotlin's, TestClientCachePolicy, TestClientHardening,
  TestTableBoundedOps).
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

| #   | Risk                                                                            | Mitigation                                                                                              |
| --- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| R1  | Jackson can't instantiate models (no creator)                                   | §2.3.1 public no-arg ctor in EVERY model; F1.13(a) gate                                                 |
| R2  | Generic deser of `VecOrValue<MaybeSpecialOrError<T>>`                           | §2.3.4 field-level `@JsonDeserialize` + ContextualDeserializer; F1.13(b) nested gate, decode AND encode |
| R3  | Package-vs-directory mismatch breaks javac/Gradle                               | §2.3.5 verify-first compile proof in F1.13(e); fallback directory layout                                |
| R4  | `jackson-datatype-jsr310` shadows Duration serializer                           | Exclude dep; never findAndRegisterModules(); F1.13(c) numeric-seconds assert                            |
| R5  | Java keyword collision (no escape mechanism)                                    | `_java_ident()` `_`-suffix rename + unit tests incl. literals and `_`                                   |
| R6  | URL encoding (`+`, spaces, path vs query)                                       | §2.3.9 verify-first spike; TestClientUrlEncoding; live formula round-trip                               |
| R7  | `Math.exp(1.0)` ULP mismatch vs Airtable                                        | Port Kotlin's EXP pin verbatim; runtime parity tests                                                    |
| R8  | Transpiler emits Kotlin-isms for Java (bare `V()`/`S()`/`N()`, `JsonPrimitive`) | §3.1 explicit enumeration incl. `_emit_str`/`_emit_num`; test_formula_transpiler_java.py                |
| R9  | Disambiguated lookup/rollup fields skip Java types                              | F1.3 explicit `map_types()` + `apply_disambiguated_type()` tasks + unit test                            |
| R10 | google-java-format missing / fights generated style                             | `command -v` guards both repos; never format generated output                                           |
| R11 | Builder + accessors balloon generated LOC                                       | Accept (idiomatic Java is verbose); offline content tests keep templates honest                         |
| R12 | JUnit cross-class parallelism racing shared records                             | Parallelism off; distinct primary keys per file                                                         |
| R13 | Jackson version churn / rogue mappers                                           | Exact pins in F1; shared `AirtableJson.MAPPER` is the ONLY mapper                                       |
| R14 | Boxed `Double` equality surprises in tests                                      | `assertEquals(42.0, x)` with Doubles; Airtable-numbers-are-Double documented                            |
| R15 | Gradle cold-start slowness in test.sh                                           | Daemon + configuration cache on (same as Kotlin)                                                        |
| R16 | Model fluent CRUD diverges from Kotlin reified extensions                       | §2.3.12 ModelOps + generated covariant methods; TestOrmCrudViaModel parity                              |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py java <folder>` generates a compiling Java source set.
- [ ] `uv run main.py all --java-folder=…` works alongside other languages.
- [ ] `./checks.sh` (myairtable) green with Java included.
- [ ] `./test.sh all` (myairtable-tests) green with Java included (seven languages).
- [ ] All ten integration test files green (struct/orm crud ×3, serializing, filter,
      runtime, caching, linked, complex, special-deser).
- [ ] Unit-test parity: 16 java_static files matching Kotlin's inventory; formula builder + runtime counts within ±5% of Rust/Kotlin.
- [ ] Upsert + dual ID/name Fields access + DX helpers (requireId/value/withView) tested.
- [ ] Generated code is idiomatic Java 21 (records/sealed for sums, builders, unchecked
      exceptions, no Kotlin-isms).
