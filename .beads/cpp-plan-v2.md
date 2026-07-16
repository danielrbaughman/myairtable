# C++ Language Support — Implementation Plan v2

> **Changes from v1 (plan-critic round, 2026-07-15)**: fixed the two compile-breaking defects —
> `_emit_num`/`_emit_str` tails at formula_transpiler.py:~1253/~1281 hand-build `{_runtime}.N(...)`
> with a literal `.` and bypass `_rt()`, so every arithmetic/comparison/concat formula would emit
> invalid `runtime.N(...)`; cpp branches added + an EARLY targeted transpiler test for `{Field}+1`
> and `{Field}&"x"` in F1, not F8 (**CRIT-1**); the `VecOrValue`/`MaybeSpecialOrError` sketches gain
> **public constructors** so `adl_serializer::from_json` can actually construct them (**CRIT-2**).
> Dropped the global `adl_serializer<std::optional<T>>` specialization entirely — hijacking a std
> type is a program-wide ODR/collision surface in a header-only library; replaced with owned
> `read_field<T>`/`write_field` helpers (**HIGH-1**). Added the missing **typecast** write-flag
> support + `test_typecast_option.cpp` (**HIGH-2**); a **ThreadSanitizer** build variant for the
> cache-concurrency test, mirroring Go's `-race` (**HIGH-3**); corrected the integration-suite
> parity claim — C# = 20 scenario files (incl. `TestSerializingIntegration`) + 5 infra, Java = 19 + 2;
> canonical C++ target = **the C# 20-file scenario set** (fullest, most recent) with Catch2-native
> infra (**HIGH-4**); the curl client keeps per-request easy handles but adds a **`CURLSH*` share**
> (DNS + TLS-session caches) so every call isn't a fresh handshake (**HIGH-5**). Added
> `test_table_bounded_ops.cpp` to F4 (**MED-1**); malformed-pattern `try/catch(std::regex_error)`
> parity in `runtime_regex.hpp` — C# returns false, `std::regex` throws (**MED-2**); a Catch2
> declaration-order micro-proof in the F1.13 gate (**MED-3**); the `SWITCH` signature is now decided:
> `initializer_list` flat pairs (**MED-4**); SET_TIMEZONE flips to **vendored Hinnant date/tz
> (USE_OS_TZDB=1, stb-style implementation macro)** as primary — a hand-rolled TZif reader was the
> wrong risk/reward for a 2-test surface (**MED-5**); new risk row R21 + pinning unit test for the
> public-computed-field silent-drop divergence (**MED-6**); GCC designated-init claim softened to
> "unverified, not CI-gated" (P1975 DR timing) (**LOW-1**); F2 gains a mid-feature real-generated-
> model compile checkpoint before the full runtime lands (**LOW-2**).

## 1. Overview & Goals

Add full-parity **C++** code generation to `myairtable` — the tenth target, alongside Python,
TypeScript, JavaScript, Rust, Go, Swift, Kotlin, Java, and C#. The closest structural template is
**C#** (`src/generators/csharp.py`, 614 lines, newest and tightest design); the closest _cultural_
templates are **Rust** (value semantics, snake_case, aggregate-style models) and **Java/C#**
(boxed JSON-node runtime value, sum-type wrappers, one-public-type-per-file). The generated code
must feel **idiomatic modern C++20** — not Java-with-headers: aggregate structs with designated
initializers, `std::optional<T>` fields, value-semantic `nlohmann::json`, RAII, `snake_case`
members, header-only distribution.

**Scope:**

- Generator at `src/generators/cpp.py` + `src/utils/write_to_cpp_file.py`
- Static runtime at `static/cpp/` (custom Airtable client over **libcurl**; **nlohmann/json**
  vendored single-header; vendored **Hinnant date/tz** for SET_TIMEZONE; no third-party SDK)
- Type mapping (`GENERIC_TO_CPP`) + formula transpiler C++ emitter (~40 arms + 2 tail fixes)
- Unit tests: `tests/test_generators.py` C++ classes (~30), `tests/test_formula_transpiler_cpp.py`
  (~44 cases), `tests/cpp_static/` Catch2/CMake project (**18 test files = C# static inventory**,
  ~420+ cases — `test_airtable_runtime.cpp` alone is 184)
- Integration tests at `myairtable-tests/cpp/` — **the C# 20-scenario-file set** (the fullest suite;
  Java has 19 — C# adds `TestSerializingIntegration`) + Catch2-native infra (`test_setup`,
  `test_harness`; no orderer/fixture files needed — §2.4)
- CLI wiring (`main.py cpp` + `all --cpp-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`, `.gitignore` (`cpp/output/`, `cpp/build/`)

**Non-goals (v1):** async/coroutine API (sync blocking matches Java/Go/Python); CMake
package/config emission by the generator (no target emits build files); C++20 modules; Windows/MSVC
(only AppleClang is CI-gated; code stays portable-in-spirit); Conan/vcpkg packaging; `operator==`
filter-DSL sugar (future enhancement); connection-pool tuning beyond the `CURLSH*` share (§2.3.8).

## 2. Design Decisions

### 2.1 User-approved (2026-07-15)

| #   | Question       | Answer                                                             |
| --- | -------------- | ------------------------------------------------------------------ |
| 1   | C++ standard   | **C++20** (designated initializers, concepts; AppleClang 21 ready) |
| 2   | HTTP + JSON    | **libcurl** (system) + **nlohmann/json** (vendored single header)  |
| 3   | Errors         | **Exceptions** — `AirtableException` + 7 variants (parity set)     |
| 4   | Test framework | **Catch2 v3** (unit + integration), via CMake FetchContent         |

Build tooling: **CMake ≥ 3.25** + system clang. Hand-written `CMakeLists.txt` in the two test
projects only. Toolchain gap on this machine: `brew install cmake ninja` is an F1 task; both
`checks.sh` blocks get `command -v cmake` warn-skip guards (Swift/Kotlin pattern).

### 2.2 C#-pattern → C++ idiom mapping

| C# construct                                                 | C++ equivalent                                                                                                   |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `sealed class AirtableClient` + `HttpClient`, async          | `class AirtableClient` + libcurl easy API + `CURLSH*` share, **sync blocking** (Java/Go model), thread-safe      |
| Mutable class + parameterless ctor + auto-properties         | **Aggregate struct** + public `std::optional<T>` members (§2.3.1)                                                |
| `JsonNode` (mutable DOM, JSON null = C# null)                | **`nlohmann::json`** (value semantics; JSON null = `json(nullptr)` — a _value_, no null-pointer state)           |
| Object initializer `new M { X = 1 }`                         | **Designated initializer** `M{.x = 1}` (compile-verified on AppleClang 21, incl. empty CRTP base)                |
| `abstract record VecOrValue<T>` + `JsonConverterFactory`     | Class template wrapping **`std::variant`** + public ctors + **`adl_serializer` partial specialization** (§2.3.4) |
| enum + generated per-enum `JsonConverter`                    | `enum class` + **generated `to_json`/`from_json`** per enum (§2.4)                                               |
| `AirtableException : Exception` + 7 sealed subclasses        | `AirtableException : std::runtime_error` + 7 subclasses (§2.3.7)                                                 |
| `async Task<T> …Async(ct)`                                   | Plain blocking `T method()` (no ct; parity with Java/Go/Py)                                                      |
| `static class AirtableRuntime` (single transpiler qualifier) | **`namespace runtime`** inside `myairtable` — free functions, reopened across headers (§2.3.3)                   |
| `PrimaryModel.F.PrimaryKey.Eq("x")`                          | `PrimaryModel::F.primary_key.eq("x")` (inline static member on the aggregate — compile-verified)                 |
| `@`-verbatim keyword escape                                  | **No escape exists** → `_cpp_ident()` appends `_` (Java-style rename); reserved set incl. alt tokens (§2.3.5)    |
| `DateTimeOffset` + custom converter                          | `std::chrono::system_clock::time_point` + hand-rolled ISO-8601 codec (§2.3.6)                                    |
| `TimeSpan`, wire = numeric seconds                           | `std::chrono::duration<double>` (seconds), wire = numeric seconds                                                |
| Per-model `SaveAsync/FetchAsync/DeleteAsync` → `ModelOps`    | CRTP base **`AirtableModel<T>`** supplies `save()/fetch()/remove()` (§2.3.12; `delete` is a C++ keyword)         |
| Partial classes `AirtableRuntime{Math,…}.cs`                 | Namespace reopened across `runtime_{logic,math,string,date,array,regex}.hpp`                                     |
| `namespace MyAirtable;` file-scoped, folders organizational  | `namespace myairtable` everywhere; folders organizational only — **no include-path-vs-namespace gate**           |

### 2.3 C++-specific decisions

#### 2.3.1 Model shape: aggregate struct + public `std::optional<T>` members + empty CRTP base (VERIFIED on AppleClang)

```cpp
struct PrimaryModel : AirtableModel<PrimaryModel> {   // empty CRTP base → still an aggregate
    // -- record meta (direct members; base holds NO data) --
    std::optional<std::string> id{};
    std::optional<std::string> created_time{};
    std::shared_ptr<AirtableClient> client_{};        // attached client (internal, trailing _)
    nlohmann::json snapshot_{};                       // dirty-tracking snapshot (internal)

    // -- writable --
    std::optional<std::string> primary_key{};         /// Single Line Text `fldXXX`
    // -- computed (public but never serialized on write — see R21) --
    std::optional<MaybeSpecialOrError<int64_t>> auto_number{};

    nlohmann::json collect_writable_fields() const;   // generated hook (all writables incl. nullopt→null)
    nlohmann::json collect_computed_fields() const;   // generated hook
};
auto m = PrimaryModel{.primary_key = "x"};            // creation idiom (COMPILE-VERIFIED)
```

- **Aggregate rules hold**: no user ctors, public members, empty public base → designated
  initializers work; base is value-initialized. Verified in a scratch compile on AppleClang 21
  (incl. `inline static const Filters F` member and member functions). GCC/MSVC: **unverified and
  not CI-gated** — designated-init-with-base rests on the P1975 DR whose adoption lagged in some
  GCC releases; noted in README, not a gate (LOW-1).
- **Computed fields are public members** (no `private set` in an aggregate). Read-only-ness is
  enforced by write paths only: `collect_writable_fields()` excludes them, so
  `model.auto_number = …; model.save();` **compiles but the mutation is silently not sent** — a
  real divergence from all nine other targets (compile error there). Mitigations: risk row **R21**;
  a **pinning unit test** asserting a mutated computed field is absent from the save payload;
  prominent doc comment on every generated computed member (MED-6).
- **Internal members** (`client_`, `snapshot_`) use trailing underscore + doc comment; designated
  initializer users omit them. Same pinning test asserts they never serialize.
- `std::optional<T>` for every field: absent and JSON-null both decode to `nullopt`. **No global
  `adl_serializer<std::optional<T>>` specialization** — see §2.3.4 (HIGH-1).
- Generated per-model `from_json`/`to_json` free functions (ADL) keyed on **field IDs**, built on
  the owned `read_field<T>`/`write_field` helpers; decode wholesale, encode = writable-only hooks.
- Dirty tracking: `take_snapshot()` stores `collect_writable_fields()`; `dirty_fields()` diffs via
  nlohmann deep `operator==` (structural — the `JsonNode.DeepEquals` analog; never formula-coercion
  equality, the C# multi-value-shrink lesson).

#### 2.3.2 Filter DSL: snake_case named methods, `eq`/`neq`

C++ has no `object.Equals` footgun, but `eq`/`neq` are short and C++-culturally normal
(cf. `std::ranges::equal_to`). Full set mirrors C#: `eq/neq/contains/starts_with/greater_than/
less_than/…/is_empty/is_not_empty`. Accessor: `inline static const PrimaryFilters F{};` →
`PrimaryModel::F.primary_key.eq("x")`. `operator==` sugar deferred (non-goal).

#### 2.3.3 `nlohmann::json` is the type-erased value; ALL coercions in `namespace runtime`

The formula runtime operates on `nlohmann::json` by value/const-ref (deep value `operator==`; no
reference-equality trap exists). BLANK = `json(nullptr)`.

- Coercion helpers `v/n/s/a/an/as_v/d/is_truthy/is_equal/is_blank` are **free functions in
  `myairtable::runtime`**, alongside ~90 UPPERCASE formula functions, reopened across
  `runtime_{logic,math,string,date,array,regex}.hpp` (C# partial-class analog).
- Transpiler `_runtime = "runtime"` with a **`::` separator**: `_rt()` gains a cpp branch emitting
  `runtime::{name}`, **and the `_emit_num`/`_emit_str` qualified-default tails
  (formula_transpiler.py ~:1281/~:1253) get explicit cpp branches** — they hand-build
  `f"{_runtime}.N(...)"` with a literal `.` and bypass `_rt()`, which would emit invalid
  `runtime.N(...)` for every arithmetic/comparison operand and every non-literal concat operand
  (**CRIT-1** — the highest-blast-radius defect the critic found; pinned by an early F1 unit test
  on `{Field} + 1` and `{Field} & "x"`).
- `v(...)` is an **overload set** (the C++ answer to C#'s `object?` boxing): `v(json)` passthrough;
  `v(std::nullptr_t)`; `v(const std::optional<T>&)` → null or `v(T)`; `v(bool/int64_t/double/
const char*/std::string/time_point/duration/vector<T>)`.
- **`is_equal(a, b)`**: N/S cross-type coercion first, then structural `a == b`. Transpiler
  equality arms use number/string fast paths (`n()`/`s()` compares) with `is_equal` fallback (C# model).
- **Number emission parity**: nlohmann stores int vs double distinctly; `s()` ports the C#/Go
  number→string logic (`1` not `1.000000`). Tests use `42.0` (Airtable numbers are double).
- **`and`/`or`/`not`/`xor` are C++ alternative TOKENS** (illegal as identifiers). The transpiler
  inlines these as `is_truthy(a) && is_truthy(b)` (C# arms), and the runtime never defines them —
  but `_cpp_ident()` MUST cover the alternative-token set for field-name escaping.
- `TRUE`/`FALSE` runtime functions: legal identifiers, but system headers can `#define TRUE 1`.
  Guard with `#pragma push_macro`/`#undef` around the declarations; Phase-0 gate probes the
  collision (include `<curl/curl.h>` + runtime headers in one TU); rename to `TRUE_`/`FALSE_` only
  if the guard proves insufficient. The transpiler never calls them (`v(true)` is emitted directly).

#### 2.3.4 Sum types: `std::variant` wrappers with PUBLIC constructors + `adl_serializer` partial specializations; NO std-type specializations

```cpp
template <typename T>
class VecOrValue {
  public:
    VecOrValue() = default;                                  // decode scaffolding
    explicit VecOrValue(T single);                           // public ctors — adl_serializer
    explicit VecOrValue(std::vector<T> multiple);            //   constructs via these (CRIT-2)
    std::optional<T> value() const;                          // Single only
    std::vector<T> values() const;                           // both shapes; Single → [x]
    std::vector<T> clean_values() const;                     // nested-MSE flattening parity
    const std::variant<T, std::vector<T>>& raw() const;      // std::visit escape hatch
  private:
    std::variant<T, std::vector<T>> data_;
};
template <typename T>
class MaybeSpecialOrError {
  public:
    MaybeSpecialOrError() = default;
    explicit MaybeSpecialOrError(T value);
    explicit MaybeSpecialOrError(SpecialNumber s);
    explicit MaybeSpecialOrError(ErrorValue e);
    std::optional<T> value() const;                          // nullopt unless Value case
    bool is_special() const;  bool is_error() const;
    std::optional<SpecialNumber> special() const;  std::optional<ErrorValue> error() const;
  private:
    std::variant<T, SpecialNumber, ErrorValue> data_;
};
```

- nlohmann's `JsonConverterFactory` analog is **partial specialization of
  `nlohmann::adl_serializer<VecOrValue<T>>` / `<MaybeSpecialOrError<T>>`** — automatic, recursive
  (nested `VecOrValue<MaybeSpecialOrError<T>>` resolves by template recursion), zero registration.
  Construction goes through the **public constructors above** — v1's private-`data_`-no-ctor sketch
  could not compile (CRIT-2).
- **We specialize `adl_serializer` ONLY for types we own** (+ full specializations for our date/
  duration wrapper codecs invoked explicitly, not via ADL on std types). The v1 plan's global
  `adl_serializer<std::optional<T>>` is **dropped**: specializing a std type in a header-only
  library is a program-wide customization point — a consumer (or future nlohmann) defining the same
  specialization means duplicate-definition errors or silent ODR violations (**HIGH-1**). Instead
  `airtable_json.hpp` provides owned helpers:
  `template <typename T> std::optional<T> read_field(const json& fields, const char* id)` (absent
  or null → nullopt) and `void write_field(json& out, const char* id, const std::optional<T>&)`
  (nullopt → JSON null) — generated `from_json`/`to_json` call these per field.
- **Phase-0 gate proves decode AND encode** for: `optional<T>` via read/write helpers,
  `MaybeSpecialOrError<string|double|time_point>`, `VecOrValue<string>`, `VecOrValue<time_point>`,
  nested `VecOrValue<MaybeSpecialOrError<string>>`, null-valued computed field.

#### 2.3.5 Naming, layout, keyword escape

- `namespace myairtable` (single, flat). Folders `models/ options/ types/ formulas/ tables/`
  organizational only.
- **Files**: `snake_case.hpp`. **Types**: PascalCase. **Functions/members**: snake_case via
  `name_snake()`. **Enum class + entries**: PascalCase (`_choice_to_entry()` port). Runtime formula
  functions: UPPERCASE (all-target parity).
- **Header-only static runtime**: every function `inline`; C++17 `inline` variables for globals.
  Consuming = add `output/` to include path + link `libcurl` (+ one stb-style TU macro for tz —
  §2.3.6). One exception to pure header-only, documented there.
- `_cpp_ident()`: appends `_` to C++ keywords + alternative tokens (`and or not xor bitand bitor
compl not_eq and_eq or_eq xor_eq`) + contextual `final/override` (defensive); fixes identifiers
  that would start `_[A-Z]` or contain `__` (implementation-reserved).
- Includes: generated files include from output root (`#include "static/vec_or_value.hpp"`);
  static files include each other bare; vendored json included ONLY via the `airtable_json.hpp`
  choke point.

#### 2.3.6 Date / Duration / numbers (libc++ reality: NO chrono tz — compile-verified)

AppleClang 21's libc++ **lacks `locate_zone`/`zoned_time`/`chrono::parse`** (verified 2026-07-15);
`std::format` works. Therefore:

- Datetime = `std::chrono::system_clock::time_point` (UTC). Hand-rolled ISO-8601 codec in
  `airtable_date.hpp`: decode fractional-ISO → plain ISO (assume UTC) → date-only `YYYY-MM-DD`
  (midnight UTC); **encode millis+Z** (C# live-caught: higher precision is rejected by date columns).
- Civil-date math (YEAR/…/WEEKDAY/WEEKNUM/WORKDAY/DATEADD/DATETIME_DIFF): Hinnant
  `days_from_civil`/`civil_from_days` algorithms (~40 lines, public domain) — all UTC, no tz needed.
- `DATETIME_FORMAT`/`DATETIME_PARSE`: **moment-style token** translator ported from C#/Java.
- **`SET_TIMEZONE`**: **vendor Hinnant `date.h` + `tz.h`/`tz.cpp` with `USE_OS_TZDB=1`**
  (reads `/usr/share/zoneinfo`; no download). v1's hand-rolled TZif reader is DROPPED — correct
  TZif handling (POSIX-TZ extrapolation, rule edge cases) is far beyond "150 lines" and a subtle
  DST bug is exactly what a 2-test surface won't catch (MED-5). Since `tz.cpp` must be compiled
  once, expose it **stb-style**: `#define MYAIRTABLE_TZ_IMPLEMENTATION` in exactly one consumer TU
  (each test project does this in one file; documented in the generated README header). Unknown
  zone → same error behavior as C# (2 pinned unit tests).
- Duration = `std::chrono::duration<double>` (seconds); wire = numeric seconds.
- Numbers: `double` always (`optional<double>`); autonumber/count → `int64_t`. **`std::exp(1.0)`
  ULP check** vs Airtable `Math.E`; pin `EXP(1.0)` if needed (JVM precedent).

#### 2.3.7 Errors: exception hierarchy rooted in `std::runtime_error`

`class AirtableException : public std::runtime_error` + **7** subclasses: `HttpError{status, body}`,
`ApiError{code, message}`, `DecodingError`, `InvalidUrlError`, `MissingCredentialsError`,
`NetworkError` (CURLE\_\* transport failure ≠ HTTP status), `RateLimitedError{retry_after_seconds}`.
All carry formatted `what()`. Tests `catch (const HttpError& e)`.

#### 2.3.8 Concurrency: sync blocking; thread-safe client & cache; CURLSH share

- **Blocking API** (Java/Go model). No coroutines/cancellation (non-goal).
- **libcurl discipline**: `curl_global_init` once via `std::call_once`; **one easy handle per
  request** (easy handles aren't thread-safe) **+ a process-lifetime `CURLSH*` share** with
  `CURL_LOCK_DATA_DNS` + `CURL_LOCK_DATA_SSL_SESSION` and mutex lock callbacks, attached to every
  handle — without it each call pays fresh DNS + full TLS handshake, putting the ~20-file
  sequential live suite in a different latency/flakiness class than every other target (**HIGH-5**).
  RAII wrappers (`CurlHandle`, `CurlShare`). Full connection-pool tuning stays a non-goal.
- **CacheStore**: TTL + LRU behind `std::mutex`, **split-lock** check-fetch-store; per-table
  `invalidate(table_id)` + `invalidate_all()`; **never cache a list page carrying a live `offset`
  token** (C# late-caught bug, ported). **Cache-concurrency integration test runs under a
  `-fsanitize=thread` build variant** — the C++ analog of Go's `-race` in test.sh, and a data race
  here is UB, not an exception (**HIGH-3**); guarded/skippable like every toolchain dependency.
- **Retry**: 429 + 5xx, `Retry-After` else exponential backoff **+ jitter** (`std::mt19937` seeded
  once), `std::this_thread::sleep_for`. Transport errors → `NetworkError`.
- **`typecast`**: per-request opt-in flag on create/update/upsert bodies — full parity feature with
  dedicated C# coverage that v1 omitted entirely (**HIGH-2**); surfaced on dict + ORM write paths,
  pinned by `test_typecast_option.cpp` (unit, FakeTransport) like `TestTypecastOption.cs`.
- Pagination: eager `std::vector<T>` accumulation (parity).

#### 2.3.9 URL encoding verify-first

`curl_easy_escape` → `%2B` for `+` (correct side of the Swift/Ktor bug). Wrap as `url_encode()`;
verify-first live spike: `filterByFormula` of `LEN({field})+1` round-trips (pinned by
`test_client_url_encoding.cpp` + first live filter test). `returnFieldsByFieldId=true` on
single-record GET **and** in create/update bodies (C# live-caught).

#### 2.3.10 Formatter: clang-format

`.clang-format` at both repo roots (LLVM base, 100-col). `checks.sh` guards with
`command -v clang-format` (fallback `xcrun --find clang-format`); scope: `static/cpp` (excluding
`vendor/`), `tests/cpp_static`, `myairtable-tests/cpp/tests` — never generated output, never
vendored headers. Generator emits clang-format-clean output. No clang-tidy in v1 (parity: no
target lints beyond format+compile).

#### 2.3.11 Creation idiom: designated initializers (no builder)

`PrimaryModel{.primary_key = "x", .number = 42.0}` — compile-verified. C++20 requires
designators in declaration order; the generator emits fields in schema order and partial lists
skip freely — documented in the generated header comment.

#### 2.3.12 Model DX: CRTP `AirtableModel<T>` base (empty of data)

`template <typename Derived> struct AirtableModel` supplies behavior only: `save()`, `fetch()`,
**`remove()`** (`delete` is reserved — the one forced naming divergence; tables get
`remove(id)`/`remove_all()`), `is_new()`, `take_snapshot()`, `dirty_fields()`, `to_record()`,
`to_create_fields()`, `require_id()`, `require_client()` — implemented once against
`static_cast<Derived*>(this)` + the two generated hooks. Templates = reified generics; no
`ModelOps` token dance.

### 2.4 Other settled choices

| Decision            | Value                                                                                                                                                                                                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Test framework      | Catch2 v3 via FetchContent (pinned tag); `catch_discover_tests`+CTest in unit project; single sequential binary + tags in integration project                                                                                                                      |
| Integration phasing | Catch2 TEST_CASEs run in declaration order within a TU — CRUD phases = ordered TEST_CASEs + file-local state struct; **ordering is PROVEN in the F1.13 gate** (3-case counter micro-spec run via the same binary+tag invocation test.sh uses), not assumed (MED-3) |
| Test parallelism    | OFF by construction (one sequential binary); distinct PKs per file (`"Cpp {suite} {label} {ms}-{rand}"`); per-case cleanup + final sweep                                                                                                                           |
| Select-option enums | `enum class` PascalCase; **generated `to_json`/`from_json` per enum** keyed on raw Airtable strings (NOT `NLOHMANN_JSON_SERIALIZE_ENUM` — unknown→first-entry default breaks parity); dedup v2/v3                                                                  |
| Linked records      | Raw `std::optional<std::vector<std::string>>` IDs; resolve via `airtable.secondary().get(ids)`                                                                                                                                                                     |
| Table accessors     | `airtable.primary()` methods → lightweight table structs (hold `shared_ptr<AirtableClient>`); ORM default, `.dict()` raw (C# post-epic default)                                                                                                                    |
| Root object         | `class Airtable` — `(api_key)`, `(api_key, cache_seconds)`, `(shared_ptr<AirtableClient>)`; `invalidate_all_caches()`                                                                                                                                              |
| Fields dual access  | `Fields::get(id_or_name)` ID-first name-fallback; `{Table}Fields` emits `k{Field}Id`/`k{Field}Name` + both maps                                                                                                                                                    |
| Upsert              | `upsert(model, merge_field_ids)` incl. multi-match error path (Rust/C# parity)                                                                                                                                                                                     |
| Doc comments        | `///` Doxygen-style; field name, ID, formula text in fenced block                                                                                                                                                                                                  |
| String functions    | **UTF-8 code-point semantics** (LEN/LEFT/RIGHT/MID — Rust/Go precedent); utf8 helper in `runtime_string.hpp`                                                                                                                                                       |
| Regex               | `std::regex` ECMAScript; **malformed pattern → `catch (const std::regex_error&)` degrade matching C# (`REGEX_MATCH("(", …)` returns false, never throws)** (MED-2); 3 parity cases early in F8                                                                     |
| Version handle      | `my_airtable_runtime_info.hpp` — `constexpr std::string_view kVersion` (harness smoke)                                                                                                                                                                             |

## 3. File Layout & Integration Points

### 3.1 Source repo (`myairtable`) — ~52 edit sites

```
src/generators/cpp.py                 # NEW ~650-900 LOC (mirror csharp.py: write_options /
                                      #   write_field_types / write_formula_helpers / write_models /
                                      #   write_tables / write_main / generate_cpp)
src/utils/write_to_cpp_file.py        # NEW WriteToCppFile(WriteToFile): _cpp_ident() (keywords +
                                      #   alt tokens + reserved patterns), _cpp_string_literal(),
                                      #   doc-comment escape, _choice_to_entry() port, #pragma once
src/utils/type_mapper.py              # MOD: GENERIC_TO_CPP (~:190); "cpp" in Language Literal (:382);
                                      #   LANGUAGE_CONFIGS["cpp"] {unknown="nlohmann::json",
                                      #   list_fmt="std::vector<{0}>", union_fmt="VecOrValue<{0}>",
                                      #   NO computed_union_fmt}; map_cpp_type();
                                      #   apply_cpp_computed_wrapping(); is_already_list cpp arm
                                      #   ("std::vector<") (:493); map_types pass-1 (~:258/:267) +
                                      #   pass-2 (~:283); **idempotency guard (:238) ALSO checks
                                      #   _cpp_type** (CRIT, C# precedent); apply_disambiguated_type
                                      #   cpp branch (~:1031). optional<> wrapping happens in the
                                      #   GENERATOR (same layer C# appends `?`)
src/utils/write_to_file.py            # MOD: "cpp" in Literal (:49) + //-header case (:74)
src/meta.py                           # MOD: _cpp_type PrivateAttr (~:385) + cpp_type property (~:624)
src/formulas/formula_transpiler.py    # MOD: full checklist §3.4 (incl. the two TAIL fixes)
main.py                               # MOD: import; cpp command (~:256); all --cpp-folder (~:417/:488)
checks.sh                             # MOD: C++ block — cmake guard; configure+build+ctest
                                      #   tests/cpp_static; clang-format (excl. vendor/)
static/cpp/                           # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestCpp{ComputedTypes,WriterHelpers,Generator,
                                      #   ComputedFields,Models} (~30); BOTH field-dict factories
                                      #   (:77-89 AND :474-486) gain "_cpp_type": None
tests/test_formula_transpiler_cpp.py  # NEW ~44 cases; MUST include `{Field}+1`, `{Field}>10`,
                                      #   `{Field}&"x"` asserting runtime::n(...)/runtime::s(...)
                                      #   with `::` (CRIT-1 pin) — written in F1, not F8
tests/cpp_static/                     # NEW CMake+Catch2; FetchContent Catch2; include ../../static/cpp
  └── test_*.cpp                      #   18 files = C# static inventory; test_poco_model.cpp = GATE
.clang-format                         # NEW (repo root)
```

### 3.2 Generated output (per run)

```
<output>/
├── dynamic/{options,types,formulas,models,tables}/*.hpp
├── static/                         copied verbatim from static/cpp/ (incl. vendor/)
└── airtable.hpp                    root entry point
```

All `namespace myairtable`, header-only (+ one `MYAIRTABLE_TZ_IMPLEMENTATION` TU). Consumers: add
`<output>` to include path, link `libcurl`.

### 3.3 Test repo (`myairtable-tests`)

```
cpp/
├── CMakeLists.txt                # HAND-WRITTEN: FetchContent Catch2; include_directories(output);
│                                 #   find_package(CURL); ONE sequential binary from tests/*.cpp;
│                                 #   optional -fsanitize=thread variant target (cache tests)
├── output/                       # regenerated by build.sh (gitignored)
└── tests/
    ├── test_setup.hpp/.cpp       # .env walker; make_airtable(cache_seconds)/bad-key factory;
    │                             #   primary_key(suite,label); MYAIRTABLE_TZ_IMPLEMENTATION TU
    ├── test_harness.cpp          # smoke: kVersion + declaration-order + tag-filter wiring
    └── test_<scenario>.cpp       # 20 scenario files = C# scenario set (§5): struct_crud_via_table,
                                  #   orm_crud_via_table, orm_crud_via_model, linked_records,
                                  #   complex_properties, serializing, serializing_integration,
                                  #   special_error_deser, caching, cache_concurrency, error_paths,
                                  #   field_round_trip, filter_by_formula, formula_escaping,
                                  #   multi_field_sort, pagination, primary_formula_runtime,
                                  #   runtime_formulas, runtime_formula_variety, upsert_depth
build.sh                          # MOD: --cpp-folder "$AIRTABLE_DIR/cpp/output"
test.sh                           # MOD: usage text; `all` loop += cpp; cpp) dir arm; suite→TEST_CMD
                                  #   block (cmake --build then ./build/cpp_tests "[tag]"); execute
                                  #   branch; cache suite uses the TSan variant when available
checks.sh                         # MOD: guarded cmake build (output/ against tests/) + clang-format
.gitignore                        # MOD: cpp/output/, cpp/build/
.clang-format                     # NEW (repo root)
```

Note on parity accounting (HIGH-4): C# = **20 scenario files + 5 infra** (AssemblyInfo, CrudFixture,
PriorityOrderer, TestHarness, TestSetup); Java = **19 + 2** (no SerializingIntegration). C++ targets
the **C# 20-file scenario set** — the fullest and most recent — and needs only 2 infra files because
Catch2's sequential declaration-order execution replaces the orderer/fixture/assembly machinery.

Suite→tag map: `[crud]` struct/orm-table/orm-model/pagination/error-paths/field-round-trip/
upsert-depth · `[json]` serializing + serializing-integration · `[filter]` filter/escaping/sort ·
`[runtime]` runtime ×3 · `[cache]` caching/concurrency.

### 3.4 `formula_transpiler.py` cpp arms — explicit checklist (F8.1; items 24-25 are the v2 additions)

1. `"cpp"` in `Language` Literal (:21).
2. `_self` (:324-329): cpp arm → `"this"` (FieldRef emits `this->`, see 7).
3. `_runtime` (:334): cpp → `"runtime"`; **`_rt()` (:336-341) cpp branch → `runtime::{name}`**.
4. **`_emit_function_call` guard (:501-503)**: add `"cpp"` → `_rt(name)(args)` (CRIT).
5. NumberLiteral (:363-367): `runtime::v({value})` (int vs double form preserved).
6. StringLiteral (:385-386): `runtime::v({_cpp_string_literal})`.
7. FieldRef (:425-429): `runtime::v(this->my_field)`; **field_name_map = `name_snake()` + `_cpp_ident`**.
8. `_emit_fn_record_id` (:552): `runtime::v(this->id.value_or(""))`.
9. `_emit_fn_true`/`_false` (:565/:576): `runtime::v(true/false)`.
10. `_emit_fn_blank` bare (:588-592): cpp arm → `runtime::v(nullptr)` (NOT the `"null"` default);
    with arg (:603): `runtime::v(runtime::is_blank({arg}))`.
11. `_emit_fn_not` (:621): `runtime::v(!runtime::is_truthy({arg}))`.
12. `_emit_fn_and`/`_or` (:641/:676): `runtime::v(runtime::is_truthy(a) && runtime::is_truthy(b))` / `||`.
13. `_emit_fn_xor` (:804): `runtime::v(runtime::is_truthy(l) != runtime::is_truthy(r))`.
14. `_emit_fn_if` (:842): `(runtime::is_truthy(c) ? (t) : (f))`; fallback `runtime::v(nullptr)`.
15. `_emit_fn_ifs` (:878): result init `runtime::v(nullptr)`; ternary chain.
16. `_emit_fn_switch` (:945/:988): **decided** — runtime sig
    `inline json SWITCH(const json& expr, const json& dflt, std::initializer_list<json> flat_pairs)`;
    arm emits `runtime::SWITCH({expr}, runtime::v(nullptr), {p1, v1, p2, v2, …})` (braced list) (MED-4).
17. Fall-through `None` guards (~20 sites: len/str-methods/encode*url/int/abs/sqrt/exp/log10(→LOG)/
    power/mod/regex*\*/min/max/sum/round/concatenate/rept/date_part/datetime_parse): add `"cpp"`.
18. `_emit_fn_countall` (:1040): `runtime::v(runtime::a(json::array({args})).size())`-shaped
    (finalize against the runtime `a()` signature in F8).
19. ~~falls to qualified defaults~~ **REPLACED — see 24.**
20. **`_emit_binary_op` equality (:1343-1356)**: cpp gets its own block (C# precedent): number →
    `runtime::v(runtime::n(l) == runtime::n(r))`; string → `runtime::v(runtime::s(l) == runtime::s(r))`;
    mixed → `runtime::v(runtime::is_equal(l, r))` (+ `!` negation).
21. `_emit_binary_op` arithmetic (:1326)/comparison (:1338)/concat `&` (:1431): cpp `v()` wrapping arms.
22. `_emit_unary_op` (:1447): `runtime::v(-runtime::n(x))` shape.
23. `_cpp_ident` applied to every emitted identifier path.
24. **`_emit_num` tail (~:1281) and `_emit_str` tail (~:1253)** hand-build `f"{_runtime}.N/S(...)"`
    — **add cpp branches (or route through `_rt()`)** so they emit `runtime::n(...)`/`runtime::s(...)`.
    Hit by EVERY arithmetic/comparison operand and non-literal concat operand (**CRIT-1**).
25. **Early pin test (F1)**: `test_formula_transpiler_cpp.py` cases for `{Field} + 1`, `{Field} > 10`,
    `{Field} & "x"` asserting the `::` qualifier — do not defer discovery to F8.

## 4. Static Runtime Contract (`static/cpp/`, ~36 headers + vendor)

One public type per header, all `namespace myairtable`, header-only inline (+ tz TU macro).

- `airtable_json.hpp` — includes vendored nlohmann; `using json = nlohmann::json;`;
  **`read_field<T>`/`write_field` optional helpers** (NO std-type adl_serializer — §2.3.4); shared
  decode utilities.
- `vendor/nlohmann/json.hpp` — pinned release, version comment.
  `vendor/date/date.h`, `vendor/date/tz.h`, `vendor/date/tz.cpp` — Hinnant, `USE_OS_TZDB=1`,
  stb-style `MYAIRTABLE_TZ_IMPLEMENTATION` (§2.3.6).
- `runtime.hpp` + `runtime_{logic,math,string,date,array,regex}.hpp` — coercions + ~90 UPPERCASE
  functions (C# group counts: logic 8, math 21, string 14, date 24, array 4, regex 3). `SWITCH`
  initializer_list signature (§3.4-16); regex malformed-pattern degrade (MED-2); EXP ULP pin;
  TRUE/FALSE macro guards; UTF-8 helpers.
- `airtable_date.hpp` — ISO codec (3-format decode, millis+Z encode), civil math, moment tokens,
  SET_TIMEZONE via vendored tz.
- `vec_or_value.hpp` / `maybe_special_or_error.hpp` — §2.3.4 wrappers (public ctors) + serializers.
- `special_number.hpp`, `error_value.hpp`, `airtable_attachment.hpp` (+ thumbnails),
  `airtable_collaborator.hpp`, `airtable_button.hpp`, `airtable_record.hpp`, `sort.hpp` (+ direction).
- `airtable_exception.hpp` — base + 7 (§2.3.7) + error-envelope decode.
- `airtable_client.hpp` — CurlHandle/CurlShare RAII, call_once global init, blocking endpoints,
  429+5xx retry + jitter, pagination, chunk-of-10 batching, **typecast flag**, `url_encode`,
  `returnFieldsByFieldId` everywhere, injectable transport seam (FakeTransport tests — C# CS11.1),
  owns CacheStore.
- `cache_store.hpp` — TTL+LRU, mutex split-lock, offset-page skip, invalidate/invalidate_all.
- `airtable_query.hpp`, `fields.hpp`, `dict_table.hpp`, `orm_table.hpp` (get/get-many/list/create/
  update/upsert/remove/remove_all), `airtable_model.hpp` (CRTP), `my_airtable_runtime_info.hpp`.
- Formula DSL (`_FORMULA_STATIC_FILES` exclusion set): `formulas.hpp`, `formula_field.hpp`,
  `formula_id.hpp`, `formula_text_ops.hpp`, `formula_{text,number,boolean,date,single_select,
multi_select,lookup,attachments}_field.hpp`.

**cpp_static unit inventory (18 files = C# inventory):** test_poco_model (GATE), test_airtable_runtime
(184), test_formula (98), test_airtable_query_build, test_airtable_exception_decoding,
test_special_error_decoding, test_value_coercion, test_date_decoding, test_fields_dual_access,
test_cache_store, test_client_cache_policy, test_client_hardening, test_client_retry (+ transport
seam), test_client_url_encoding, test_dx_helpers, test_table_bounded_ops, test_typecast_option,
test_value_carriers (+ fake_transport infra).

## 5. Feature Breakdown (→ beads epic, 11 features, ~75 tasks)

### F1 — Scaffolding & Infrastructure [P0]

Toolchain (`brew install cmake ninja`; clang-format probe); `.clang-format` ×2; `write_to_file.py`;
`write_to_cpp_file.py` (+escaping unit tests); full type wiring incl. **idempotency guard**;
meta.py; `main.py cpp` + `all --cpp-folder`; vendored nlohmann + Hinnant date/tz pinned;
`tests/cpp_static/` CMake skeleton; `myairtable-tests/cpp/` skeleton; build.sh/test.sh/checks.sh
(×2); `.gitignore`; **early transpiler tail-pin tests (§3.4-25)**; **1.13 PHASE-0 GATE
`test_poco_model.cpp`** (throwaway prototypes, no static/cpp dependency): (a) aggregate +
designated-init + empty CRTP base; (b) adl_serializer round-trips per §2.3.4 (public-ctor shapes,
read_field/write_field helpers, nested, time_point, null-computed — decode AND encode);
(c) duration = numeric seconds; (d) snapshot + writable-only payload diff; (e) TRUE/FALSE macro
probe (curl.h included); (f) **Catch2 declaration-order micro-proof via binary+tag invocation**
(MED-3). **Exit**: `uv run main.py cpp <dir>` runs; both CMake projects configure+build; gate
green; cpp sections wired into all four scripts.

### F2 — Static Runtime Core [P0]

Exceptions → sum types + serializers → value carriers → date codec (**tz vendoring verified
here**) → query → fields → client (retry/pagination/batching/typecast/CURLSH/url-encode spike) →
dict table → cache store. Unit tests alongside each (exception/special-error/coercion/date/fields/
cache/client\_\* via FakeTransport seam). **Mid-F2 checkpoint (LOW-2): generate a real single-field
model against the real static/cpp headers and compile it** — real include paths and namespaces,
not the gate's prototypes — before the remaining runtime lands.

### F3 — Minimal Generator → FIRST LIVE INTEGRATION [P0]

`write_options`, `write_field_types`, `write_tables` (dict access), root `airtable.hpp`; offline
content tests; **`test_struct_crud_via_table.cpp` live** — the fail-fast milestone.

### F4 — ORM Models & Model Ops [P1]

CRTP base + `write_models` + orm_table (incl. bounded ops + empty-diff skip); offline model tests;
**R21 pinning test** (mutated computed field absent from payload); `test_table_bounded_ops.cpp` +
`test_typecast_option.cpp` (unit); live orm_crud_via_table + orm_crud_via_model.

### F5 — Complex Types [P1] — live `test_complex_properties.cpp`.

### F6 — Linked Records [P1] — live `test_linked_records.cpp`.

### F7 — Formula Builder DSL [P1] — static formula\_\* headers + write_formula_helpers + F accessor;

`test_formula.cpp` (98); live filter_by_formula (18) + formula_escaping + multi_field_sort.

### F8 — Formula Runtime & Transpiler [P1] — biggest feature

~90 runtime functions with `test_airtable_runtime.cpp` ported case-for-case (184; regex degrade
cases included); transpiler arms per §3.4 + full `test_formula_transpiler_cpp.py`; generator
`evaluate_*()` methods; live runtime_formulas + runtime_formula_variety (unicode) +
primary_formula_runtime.

### F9 — Caching [P2] — cache-policy units; live caching + cache_concurrency (**TSan variant**).

### F10 — Serialization & Hardening [P2]

serializing (offline 16) + serializing_integration (null clears) + special_error_deser +
error_paths + field_round_trip + pagination + upsert_depth; client hardening/url-encoding units.

### F11 — Parity Audit & Polish [P2]

Cross-language inventory diff (18 static / 20 integration lists above); READMEs; full
checks.sh/test.sh green; count parity ±5%; idiom pass (no C#-isms; clang-format clean).

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

| #   | Risk                                                                     | Mitigation                                                                                                                                                                          |
| --- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | Designated-init aggregate breaks on real shapes                          | Compile-verified up front; gate re-proves; fallback = default-construct + assign                                                                                                    |
| R2  | adl_serializer for nested template sums                                  | Public-ctor shapes (§2.3.4); gate (b) nested + time_point + null-computed, decode AND encode                                                                                        |
| R3  | libc++ no chrono tz (VERIFIED absent)                                    | Hand ISO codec + civil math; **vendored Hinnant tz (USE_OS_TZDB)**; stb-style TU macro                                                                                              |
| R4  | DATETIME_FORMAT moment tokens ≠ strftime                                 | Port token translator; 184-case suite pins                                                                                                                                          |
| R5  | UTF-8 vs code-point semantics                                            | utf8 helpers (Rust/Go precedent); unicode variety live test                                                                                                                         |
| R6  | `std::regex` gaps; malformed pattern THROWS (C# returns false)           | try/catch degrade in all 3 REGEX\_\* (MED-2); port C# patterns early in F8                                                                                                          |
| R7  | `and/or/not/xor` alt tokens; `delete` keyword; TRUE/FALSE macros         | `_cpp_ident` alt-token set; `remove()`; push_macro guard + gate probe (e)                                                                                                           |
| R8  | Transpiler emits `runtime.X` (dot) — incl. the `_emit_num/_str` TAILS    | §3.4-3/4/**24** explicit branches; **early F1 pin tests (§3.4-25)** (CRIT-1)                                                                                                        |
| R9  | `map_types` idempotency guard omission → stale types                     | §3.1 explicit edit + unit test (C# CRIT-2 precedent)                                                                                                                                |
| R10 | Vendored headers bloat/drift                                             | Pinned versions + comments; only choke-point includes; excluded from clang-format                                                                                                   |
| R11 | curl thread-safety / per-call DNS+TLS handshakes                         | Per-request handles **+ CURLSH share (DNS+SSL_SESSION)** + call_once init (HIGH-5)                                                                                                  |
| R12 | Header-only compile times                                                | Bounded; choke points; non-goal to optimize                                                                                                                                         |
| R13 | `+` in filterByFormula                                                   | curl_easy_escape → %2B; verify-first live spike                                                                                                                                     |
| R14 | `std::exp(1.0)` ULP                                                      | Verify-first; pin EXP(1.0) if needed                                                                                                                                                |
| R15 | Date wire format rejected                                                | millis+Z from day one (C# lesson)                                                                                                                                                   |
| R16 | Catch2 ordering assumption wrong/version-dependent                       | **F1.13(f) micro-proof under the real invocation**; distinct PKs regardless (MED-3)                                                                                                 |
| R17 | cmake/ninja missing                                                      | F1 brew task; `command -v` warn-skip guards                                                                                                                                         |
| R18 | Offset-token list pages cached                                           | Port C# skip; cache unit test                                                                                                                                                       |
| R19 | int vs double json storage breaks formatting/equality                    | `n()` coerces; `s()` ports number-format logic; tests use 42.0                                                                                                                      |
| R20 | GCC/MSVC portability of aggregate+CRTP idiom                             | **Unverified, not CI-gated** (P1975 DR timing); README note (LOW-1)                                                                                                                 |
| R21 | **Public computed fields: `model.auto_number=…; save()` silently drops** | Divergence unique to C++ (compile error elsewhere); pinning unit test + doc comments on every generated computed member; snapshot*/client* likewise pinned never-serialized (MED-6) |
| R22 | Data race in split-lock CacheStore is UB, not an exception               | **TSan build variant for cache-concurrency suite** (Go `-race` precedent) (HIGH-3)                                                                                                  |
| R23 | ODR collision from specializing serializers for std types                | **Dropped std-type specializations**; owned read_field/write_field helpers only (HIGH-1)                                                                                            |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py cpp <folder>` generates a compiling C++20 header set (`cmake --build` clean).
- [ ] `uv run main.py all --cpp-folder=…` works alongside the other nine languages.
- [ ] `./checks.sh` (myairtable) green with the C++ block.
- [ ] `./test.sh all` / `./test.sh cpp --all` (myairtable-tests) green — ten languages.
- [ ] All **20** canonical integration scenario files green (C# scenario set, snake_case names) +
      harness/setup infra.
- [ ] Unit parity: **18** cpp_static files = C# static inventory (incl. typecast + bounded-ops);
      `test_airtable_runtime.cpp` = 184; `test_formula.cpp` = 98; transpiler ~44 (incl. tail pins);
      generator content ~30.
- [ ] Upsert + dual ID/name Fields + DX helpers + typecast tested; R21 pinning test present.
- [ ] Cache-concurrency green under TSan (where toolchain supports).
- [ ] Generated code is idiomatic C++20: aggregates + designated initializers, `std::optional`,
      snake_case, header-only, RAII, clang-format clean, no Java/C#-isms.
