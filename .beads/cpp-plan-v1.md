# C++ Language Support — Implementation Plan v1

> Draft for plan-critic review (2026-07-15). Tenth language target. Template: `csharp-plan-v2.md`
> (the ninth and most recent target), cross-checked against fresh code analysis of the generator,
> transpiler, unit-test, and integration-test surfaces.

## 1. Overview & Goals

Add full-parity **C++** code generation to `myairtable` — the tenth target, alongside Python,
TypeScript, JavaScript, Rust, Go, Swift, Kotlin, Java, and C#. The closest structural template is
**C#** (`src/generators/csharp.py`, 614 lines, newest and tightest design); the closest *cultural*
templates are **Rust** (value semantics, snake_case, aggregate-style models) and **Java/C#**
(boxed JSON-node runtime value, sum-type wrappers, one-public-type-per-file). The generated code
must feel **idiomatic modern C++20** — not Java-with-headers: aggregate structs with designated
initializers, `std::optional<T>` fields, value-semantic `nlohmann::json`, RAII, `snake_case`
members, header-only distribution.

**Scope:**

- Generator at `src/generators/cpp.py` + `src/utils/write_to_cpp_file.py`
- Static runtime at `static/cpp/` (custom Airtable client over **libcurl**; **nlohmann/json**
  vendored single-header; no third-party Airtable SDK)
- Type mapping (`GENERIC_TO_CPP`) + formula transpiler C++ emitter (~40 arms)
- Unit tests: `tests/test_generators.py` C++ classes, `tests/test_formula_transpiler_cpp.py`
  (~44 cases), `tests/cpp_static/` Catch2/CMake project (18 test files, C#/Java parity,
  ~420+ cases — `test_airtable_runtime.cpp` alone is 184)
- Integration tests at `myairtable-tests/cpp/` (21-file canonical scenario set = C#/Java parity)
- CLI wiring (`main.py cpp` + `all --cpp-folder`)
- `checks.sh` (both repos), `myairtable-tests/{build,test}.sh`, `.gitignore` (`cpp/output/`, build dirs)

**Non-goals (v1):** async/coroutine API (C++20 coroutines have no std IO support; sync blocking
matches Java/Go/Python); CMake package/config emission by the generator (parity: no target emits
build files); modules (`import`) — plain headers; Windows/MSVC support (checks run on macOS
AppleClang; keep code portable-in-spirit but only clang is gated); Conan/vcpkg packaging;
`operator==` filter-DSL sugar (future enhancement — named methods first).

## 2. Design Decisions

### 2.1 User-approved (2026-07-15)

| #   | Question       | Answer                                                              |
| --- | -------------- | ------------------------------------------------------------------- |
| 1   | C++ standard   | **C++20** (designated initializers, concepts; AppleClang 21 ready)  |
| 2   | HTTP + JSON    | **libcurl** (system) + **nlohmann/json** (vendored single header)   |
| 3   | Errors         | **Exceptions** — `AirtableException` + 7 variants (parity set)      |
| 4   | Test framework | **Catch2 v3** (unit + integration), via CMake FetchContent          |

Build tooling: **CMake ≥ 3.25** + system clang. Hand-written `CMakeLists.txt` in the two test
projects only (generator emits no build files — parity with all other targets). Toolchain gap on
this machine: `brew install cmake ninja` is an F1 task; both `checks.sh` blocks get
`command -v cmake` warn-skip guards (Swift/Kotlin pattern).

### 2.2 C#-pattern → C++ idiom mapping

| C# construct                                                | C++ equivalent                                                                                            |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `sealed class AirtableClient` + `HttpClient`, async         | `class AirtableClient` + libcurl easy API, **sync blocking** (Java/Go model), thread-safe                   |
| Mutable class + parameterless ctor + auto-properties        | **Aggregate struct** + public `std::optional<T>` members (§2.3.1)                                           |
| `JsonNode` (mutable DOM, JSON null = C# null)               | **`nlohmann::json`** (value semantics; JSON null = `json(nullptr)` — a *value*, no null-pointer state)      |
| Object initializer `new M { X = 1 }`                        | **Designated initializer** `M{.x = 1}` (compile-verified on AppleClang 21, incl. empty CRTP base)           |
| `abstract record VecOrValue<T>` + `JsonConverterFactory`    | Class template wrapping **`std::variant`** + **`nlohmann::adl_serializer` partial specialization** (§2.3.4) |
| enum + generated per-enum `JsonConverter`                   | `enum class` + **generated `to_json`/`from_json`** per enum (§2.4)                                          |
| `AirtableException : Exception` + 7 sealed subclasses       | `AirtableException : std::runtime_error` + 7 subclasses (§2.3.7)                                            |
| `async Task<T> …Async(ct)`                                  | Plain blocking `T method()` (no ct; parity with Java/Go/Py/Rust-blocking)                                   |
| `static class AirtableRuntime` (single transpiler qualifier)| **`namespace runtime`** inside `myairtable` — free functions, reopened across headers (§2.3.3)              |
| `PrimaryModel.F.PrimaryKey.Eq("x")`                         | `PrimaryModel::F.primary_key.eq("x")` (inline static member on the aggregate — compile-verified)            |
| `@`-verbatim keyword escape                                 | **No escape exists** → `_cpp_ident()` appends `_` (Java-style rename); reserved set incl. alt tokens (§2.3.5)|
| `DateTimeOffset` + custom converter                         | `std::chrono::system_clock::time_point` + hand-rolled ISO-8601 parse/format (§2.3.6)                        |
| `TimeSpan`, wire = numeric seconds                          | `std::chrono::duration<double>` (seconds), wire = numeric seconds                                           |
| Per-model `SaveAsync/FetchAsync/DeleteAsync` → `ModelOps`   | CRTP base **`AirtableModel<T>`** supplies `save()/fetch()/remove()` (§2.3.12; `delete` is a C++ keyword)     |
| Partial classes `AirtableRuntime{Math,…}.cs`                | Namespace reopened across `runtime_{logic,math,string,date,array,regex}.hpp`                                |
| `namespace MyAirtable;` file-scoped, folders organizational | `namespace myairtable` everywhere; headers under `models/ options/ types/ formulas/ tables/` — organizational only, **no include-path-vs-namespace gate needed** |

### 2.3 C++-specific decisions

#### 2.3.1 Model shape: aggregate struct + public `std::optional<T>` members + empty CRTP base (VERIFIED)

```cpp
struct PrimaryModel : AirtableModel<PrimaryModel> {   // empty CRTP base → still an aggregate
    // -- record meta (direct members; base holds NO data) --
    std::optional<std::string> id{};
    std::optional<std::string> created_time{};        // ISO string on wire; helper accessor
    std::shared_ptr<AirtableClient> client_{};        // attached client (internal, trailing _)
    nlohmann::json snapshot_{};                       // dirty-tracking snapshot (internal)

    // -- writable --
    std::optional<std::string> primary_key{};         /// Single Line Text `fldXXX`
    // -- computed (public but never serialized on write) --
    std::optional<MaybeSpecialOrError<int64_t>> auto_number{};

    nlohmann::json collect_writable_fields() const;   // generated hook (all writables incl. nullopt→null)
    nlohmann::json collect_computed_fields() const;   // generated hook
};
// creation idiom (COMPILE-VERIFIED on AppleClang 21, empty base + designated init):
auto m = PrimaryModel{.primary_key = "x"};
```

- **Aggregate rules hold**: no user ctors, public members, empty public base → designated
  initializers work; base is value-initialized. Verified in a scratch compile (incl. `inline
  static const Filters F` member and member functions). GCC portability: also accepted; only
  AppleClang is CI-gated.
- **Computed fields are public members** (no `private set` in an aggregate) — Rust precedent:
  read-only-ness is enforced by *write paths never serializing them* (`collect_writable_fields`
  excludes; `save()` diffs writables only). Documented, not compiler-enforced.
- **Internal members** (`client_`, `snapshot_`) use trailing underscore + doc comment; designated
  initializer users simply omit them. This is the price of the aggregate idiom and it is the same
  trade Rust makes (public struct fields).
- `std::optional<T>` for every field: absent and JSON-null both decode to `nullopt` (other targets'
  nullable semantics). Custom `adl_serializer<std::optional<T>>` (nlohmann has none built in) —
  Phase-0 gate item.
- Generated per-model `from_json`/`to_json` free functions (ADL) keyed on **field IDs**; decode
  wholesale, encode = writable-only via hooks (payloads hand-rolled, same as every target).
- Dirty tracking: `take_snapshot()` stores `collect_writable_fields()` JSON; `dirty_fields()` diffs
  current vs snapshot using nlohmann's deep `operator==` (structural — the `JsonNode.DeepEquals`
  analog; the C# lesson "don't use formula-coercion equality for dirty diff" is free here).

#### 2.3.2 Filter DSL: snake_case named methods, `eq`/`neq`

C++ has no `object.Equals` footgun, but `eq`/`neq` are short, C++-culturally normal (cf.
`std::ranges::equal_to`), and keep the C#/Java naming column. Full set mirrors C#:
`eq/neq/contains/starts_with/greater_than/less_than/…/is_empty/is_not_empty`. Accessor:
`inline static const PrimaryFilters F{};` on the model → `PrimaryModel::F.primary_key.eq("x")`.
`operator==` DSL sugar is a declared future enhancement, not in v1.

#### 2.3.3 `nlohmann::json` is the type-erased value; ALL coercions in `namespace runtime`

The formula runtime operates on `nlohmann::json` **by value/const-ref** (value semantics — no
reference-vs-value equality trap at all; `operator==` is deep structural equality). BLANK =
`json(nullptr)` (json's own null *state*, not a C++ null pointer).

- Coercion helpers `v/n/s/a/an/as_v/d/is_truthy/is_equal` are **free functions in
  `myairtable::runtime`**, alongside all ~90 formula functions (uppercase names: `SUM`, `LEFT`, …).
  The namespace reopens across `runtime_logic.hpp`, `runtime_math.hpp`, `runtime_string.hpp`,
  `runtime_date.hpp`, `runtime_array.hpp`, `runtime_regex.hpp` — the C# partial-class analog.
- Transpiler `_runtime = "runtime"` with a **`::` separator** — cpp emit arms produce
  `runtime::SUM(...)` (the existing `_rt()` produces `X.name`; the cpp arm must use `::`).
- `v(...)` is a small **overload set** (the C++ answer to C#'s `object?` boxing):
  `v(json)` passthrough; `v(std::nullptr_t)`; `v(const std::optional<T>&)` → null or `v(T)`;
  `v(bool/int64_t/double/const char*/std::string/time_point/duration/vector<T>)`. Templates make
  this cleaner than C#'s runtime switch.
- **`is_equal(a, b)`**: N/S cross-type coercion first, then structural `a == b` (nlohmann deep
  equality). Transpiler equality arms use it for the mixed/fallback case; number/string fast paths
  compare `n()`/`s()` results directly (C# model).
- **Number emission parity**: nlohmann distinguishes int/uint/double internally. `v(42)` stores an
  integer, `v(42.0)` a double, and `s()`-formatting must render `1` not `1.000000` — port the
  number→string logic from the C#/Go runtimes. Tests use `42.0` (Airtable numbers are double).
- **`and`/`or`/`not`/`xor` are C++ alternative TOKENS** (operators — illegal as identifiers). The
  transpiler never emits runtime calls for these (inlined as `is_truthy(a) && is_truthy(b)` per the
  C# arms), and the runtime never defines them — but `_cpp_ident()` MUST include the full
  alternative-token set for *field-name* escaping (a field named "or" would otherwise emit `this->or`).
- `TRUE`/`FALSE` runtime functions: legal identifiers, but system headers (`mach/boolean.h` via
  transitive includes) may `#define TRUE 1`. Mitigation: runtime headers `#pragma push_macro`/`#undef`
  guard around declarations, or the transpiler never calls them (C# emits `v(true)` directly) and
  unit tests call them from a controlled TU. Verify in Phase-0 gate; rename to `TRUE_`/`FALSE_` only
  if the guard proves insufficient.

#### 2.3.4 Sum types: `std::variant` wrappers + `adl_serializer` partial specializations (global, zero per-field wiring)

```cpp
template <typename T>
class VecOrValue {                    // wraps std::variant<T, std::vector<T>>
  public:
    std::optional<T> value() const;               // Single only
    std::vector<T> values() const;                // both shapes, Single → [x]
    std::vector<T> clean_values() const;          // VecOrValue<MaybeSpecialOrError<T>> flattening parity
    // pattern-match escape hatch: const auto& raw() / std::visit-able
  private:
    std::variant<T, std::vector<T>> data_;
};
template <typename T>
class MaybeSpecialOrError {           // wraps std::variant<T, SpecialNumber, ErrorValue>
  public:
    std::optional<T> value() const;   // nullopt unless the Value case
    bool is_special() const; bool is_error() const;  // + special()/error() accessors
  private:
    std::variant<T, SpecialNumber, ErrorValue> data_;
};
```

nlohmann's analog of `JsonConverterFactory` is **partial specialization of
`nlohmann::adl_serializer<VecOrValue<T>>`** (and `<MaybeSpecialOrError<T>>`,
`<std::optional<T>>`, plus full specializations for `time_point`/`duration`): resolution is
automatic, recursive, and needs **no registration at all** — strictly simpler than C#'s
options-level factories. Decode peek: array → `Multiple`; object with `"specialValue"` → Special;
object with `"error"` → Error; else `T`. Nested `VecOrValue<MaybeSpecialOrError<T>>` resolves by
template recursion. **Phase-0 gate proves decode AND encode for all of these incl.
`VecOrValue<time_point>` and null-valued computed fields.**

#### 2.3.5 Naming, layout, keyword escape

- `namespace myairtable` (single, flat — every static and generated file). Folders
  `models/ options/ types/ formulas/ tables/` are organizational only.
- **Files**: `snake_case.hpp` (`primary_model.hpp`). **Types**: PascalCase. **Functions/members**:
  snake_case via existing `name_snake()`. **Enum class + enumerators**: PascalCase (entries via
  `_choice_to_entry()` port). Runtime formula functions: UPPERCASE (all-target parity).
- **Header-only static runtime**: every function `inline` (or implicitly inline in-class), C++17
  `inline` variables for globals. Rationale: consuming the generated output = "add `output/` to the
  include path, link `libcurl`" — no library build step, the closest C++ gets to the drop-in-source
  experience every other target has. Compile-time cost is bounded (runtime ≈ 6–8k lines) and paid
  only by the consumer's including TUs.
- `_cpp_ident()`: appends `_` to C++ keywords + alternative tokens (`and or not xor bitand bitor
  compl not_eq and_eq or_eq xor_eq`) + `final/override` (contextual, defensive) — and rejects/fixes
  identifiers that would begin with `_` + uppercase or contain `__` (reserved to the implementation).
- Include strategy: generated files include relatively from the output root
  (`#include "static/vec_or_value.hpp"`); consumers add the output folder to their include path.
  Static files include each other bare (`#include "airtable_exception.hpp"`) — they sit in one dir.
  Vendored json at `static/cpp/vendor/nlohmann/json.hpp`, included as `"vendor/nlohmann/json.hpp"`
  via a single `airtable_json.hpp` choke point (everything else includes that).

#### 2.3.6 Date / Duration / numbers (libc++ reality: NO chrono tz — verified)

AppleClang 21's libc++ **lacks `locate_zone`/`zoned_time`/`chrono::parse`** (compile-verified
2026-07-15). `std::format` works. Therefore:

- Datetime = `std::chrono::system_clock::time_point` (UTC). **Hand-rolled** ISO-8601 codec in
  `airtable_date.hpp`: decode order fractional-ISO → plain ISO (assume UTC) → date-only
  `YYYY-MM-DD` (midnight UTC), matching every target's 3-format decode. **Write format is
  millis+Z** (`%FT%H:%M:%S.mmmZ`) — the C# live-caught lesson; date columns reject higher precision.
- Civil-date math (YEAR/MONTH/DAY/WEEKDAY/WEEKNUM/WORKDAY/DATEADD/DATETIME_DIFF): Howard Hinnant's
  public-domain `days_from_civil`/`civil_from_days` algorithms, ~40 lines, no dependency.
- `DATETIME_FORMAT`/`DATETIME_PARSE` use **moment-style tokens** (`YYYY-MM-DD`, `HH:mm`) — port the
  token translator from the C#/Java runtime (string processing, no locale).
- **`SET_TIMEZONE`**: tiny surface (2 unit tests + transpiled formulas that use it). Implement a
  **minimal TZif v2/v3 reader** (`tz_offset(zone_name, tp)` over `/usr/share/zoneinfo`, ~150-200
  lines, present on macOS/Linux). Unknown zone → same error behavior as C#. Fallback if the reader
  fights back: vendor Hinnant `date/tz.h` with `USE_OS_TZDB=1`. **Verify-first spike in F2.**
- Duration = `std::chrono::duration<double>` (seconds); wire = numeric seconds.
- Numbers: always `double` (`std::optional<double>`); autonumber/count → `int64_t`. **`std::exp(1.0)`
  ULP check** vs `M_E`/Airtable — pin `EXP(1.0)` if needed (JVM needed it; verify-first).

#### 2.3.7 Errors: exception hierarchy rooted in `std::runtime_error`

`class AirtableException : public std::runtime_error` + **7** subclasses (canonical parity set):
`HttpError{status, body}`, `ApiError{code, message}`, `DecodingError`, `InvalidUrlError`,
`MissingCredentialsError`, `NetworkError` (curl transport failure — CURLE_* ≠ HTTP status),
`RateLimitedError{retry_after_seconds}`. All carry a formatted `what()`. Tests
`catch (const HttpError& e)` — direct analog of every target's typed-error tests.

#### 2.3.8 Concurrency: sync blocking; thread-safe client & cache

- **Blocking API** (Java/Go model): `PrimaryModel get(const std::string& id)`. No coroutines, no
  cancellation token (non-goal §1).
- **libcurl discipline**: `curl_global_init` exactly once via `std::call_once`; **one easy handle
  per request** (easy handles are not thread-safe; per-request handles make the client trivially
  thread-safe — RAII wrapper `CurlHandle` with `unique_ptr` + custom deleter). Connection reuse is
  forfeited; acceptable (tests and parity, not throughput, are the goal — noted as future tuning).
- **CacheStore**: TTL + LRU behind `std::mutex`, **split-lock** check-fetch-store (lock, check,
  unlock, fetch over network, relock, store) — the C#/Rust pattern; never hold the mutex across the
  HTTP call. Per-table `invalidate(table_id)` + `invalidate_all()`. **Do NOT cache a list page that
  carries a live `offset` token** (C# late-caught bug — port the skip).
- **Retry**: HTTP 429 + 5xx, `Retry-After` else exponential backoff, **+ jitter**
  (`std::mt19937` seeded once), `std::this_thread::sleep_for`. Transport errors → `NetworkError`.
- Pagination: eager `std::vector<T>` accumulation (all-target parity).

#### 2.3.9 URL encoding verify-first

`curl_easy_escape` percent-encodes everything non-alphanumeric (`+` → `%2B` — correct side of the
Swift/Ktor bug). Wrap as `url_encode(const std::string&)`; **verify-first live spike**: a
`filterByFormula` of `LEN({field})+1` must round-trip (pinned by `test_client_url_encoding.cpp`
and the first live filter test). `returnFieldsByFieldId=true` on single-record GET **and** in
create/update bodies (C# live-caught lesson).

#### 2.3.10 Formatter: clang-format

`.clang-format` at both repo roots (LLVM base, 100-col, pointer-left — match hand-written style).
`checks.sh` blocks guard with `command -v clang-format` (fallback probe `xcrun --find clang-format`)
and format `static/cpp`, `tests/cpp_static`, `myairtable-tests/cpp/tests` — **never generated
output**. The generator emits clang-format-clean output (same discipline as CSharpier target).
No clang-tidy in v1 (no other target runs a linter beyond format+compile).

#### 2.3.11 Creation idiom: designated initializers (no builder)

`PrimaryModel{.primary_key = "x", .number = 42.0}` — compile-verified. Members must be declared in
schema order and initializers appear in declaration order (C++20 rule) — the generator already
emits fields in schema order, and partial designated lists skip freely, so this is a non-issue in
practice; documented in the generated header comment.

#### 2.3.12 Model DX: CRTP `AirtableModel<T>` base (empty of data)

`template <typename Derived> struct AirtableModel` supplies shared *behavior* only (data lives on
the aggregate — §2.3.1): `save()`, `fetch()`, **`remove()`** (`delete` is a reserved word — the one
forced naming divergence; tables likewise get `remove(id)`/`remove_all()`), `is_new()`,
`take_snapshot()`, `dirty_fields()`, `to_record()`, `to_create_fields()`, `require_id()`,
`require_client()` — all implemented once against `static_cast<Derived*>(this)` + the two generated
hooks (`collect_writable_fields`/`collect_computed_fields`). C++ templates are the reified-generics
analog: no `ModelOps` class token dance needed.

### 2.4 Other settled choices

| Decision            | Value                                                                                                        |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| Test framework      | Catch2 v3 via FetchContent (pinned tag); `catch_discover_tests` + CTest in unit project; single binary + tags in integration project |
| Integration phasing | Catch2 runs TEST_CASEs in **declaration order within a TU**, sequentially — CRUD phases = ordered TEST_CASEs sharing a file-local state struct; no orderer needed (simpler than xUnit) |
| Test parallelism    | OFF by construction (one sequential binary); distinct primary keys per file (`"Cpp StructCrud PKOnly {ts}-{rand}"`); cleanup in each case + final sweep case |
| Select-option enums | `enum class {Options}` PascalCase entries; **generated `to_json`/`from_json` per enum** keyed on raw Airtable strings (hand-rolled, NOT `NLOHMANN_JSON_SERIALIZE_ENUM` — its unknown-value→first-entry default is wrong for parity); dedup v2/v3 suffix |
| Linked records      | Raw `std::optional<std::vector<std::string>>` record IDs; resolve via `airtable.secondary().get(ids)`        |
| Table accessors     | `airtable.primary()` **methods** returning lightweight table structs (hold `shared_ptr<AirtableClient>`); ORM is the default surface, `.dict()` for the raw field-bag table (C# post-epic default) |
| Root object         | `class Airtable` — ctors: `(api_key)`, `(api_key, cache_seconds)`, `(shared_ptr<AirtableClient>)`; `invalidate_all_caches()` |
| Fields dual access  | `Fields` wrapper: `get(id_or_name)` ID-first name-fallback; `{Table}Fields` emits `k{Field}Id` + `k{Field}Name` constants + `id_by_name`/`name_by_id` maps |
| Upsert              | `upsert(model, merge_field_ids)` — parity with Rust/C# incl. multi-match error path                           |
| Doc comments        | `///` Doxygen-style; escape nothing exotic (no XML) — field name, field ID, formula text in a fenced block    |
| String functions    | **UTF-8 code-point semantics** (LEN/LEFT/RIGHT/MID count code points — Rust/Go precedent); small utf8 helper in `runtime_string.hpp` |
| Regex               | `std::regex`, ECMAScript grammar (platform-regex precedent: C#/Java/Go all use theirs); test patterns are simple — verify the 3 REGEX_* parity cases early in F8 |
| Version handle      | `my_airtable_runtime_info.hpp` — `constexpr std::string_view kVersion` (harness smoke test)                   |

## 3. File Layout & Integration Points

### 3.1 Source repo (`myairtable`) — ~50 edit sites

```
src/generators/cpp.py                 # NEW ~650-900 LOC (mirror csharp.py structure exactly:
                                      #   write_options / write_field_types / write_formula_helpers /
                                      #   write_models / write_tables / write_main / generate_cpp)
src/utils/write_to_cpp_file.py        # NEW WriteToCppFile(WriteToFile): _cpp_ident() (keyword+alt-token
                                      #   +reserved-pattern rename), _cpp_string_literal(), doc-comment
                                      #   escaping, _choice_to_entry() port, header guard/pragma-once emit
src/utils/type_mapper.py              # MOD: GENERIC_TO_CPP (~190); "cpp" in Language Literal (:382);
                                      #   LANGUAGE_CONFIGS["cpp"] {unknown="nlohmann::json",
                                      #   list_fmt="std::vector<{0}>", union_fmt="VecOrValue<{0}>",
                                      #   NO computed_union_fmt}; map_cpp_type();
                                      #   apply_cpp_computed_wrapping() (MaybeSpecialOrError<T> /
                                      #   VecOrValue<MaybeSpecialOrError<T>>, strips std::vector<...>);
                                      #   is_already_list cpp arm (startswith "std::vector<") (:493);
                                      #   map_types pass-1 (~:258/:267) + pass-2 (~:283);
                                      #   **idempotency guard (:238) ALSO checks _cpp_type** (CRIT);
                                      #   apply_disambiguated_type cpp branch (~:1031)
                                      #   NOTE: model fields are optional-wrapped by the GENERATOR
                                      #   (std::optional<{type}>) not the type map — same layer C# adds `?`
src/utils/write_to_file.py            # MOD: "cpp" in language Literal (:49) + //-comment header case (:74)
src/meta.py                           # MOD: _cpp_type PrivateAttr (~:385) + cpp_type property (~:624)
src/formulas/formula_transpiler.py    # MOD: full arm checklist §3.4
main.py                               # MOD: import; @app.command() cpp (~:256 pattern); all --cpp-folder
                                      #   (~:417 option + ~:488 dispatch)
checks.sh                             # MOD: C++ block — guard `command -v cmake`; configure+build+ctest
                                      #   tests/cpp_static; clang-format static/cpp tests/cpp_static
static/cpp/                           # NEW static runtime (§4)
tests/test_generators.py              # MOD: TestCpp{ComputedTypes,WriterHelpers,Generator,ComputedFields,
                                      #   Models} (~30 tests, C# class parity); BOTH field-dict factories
                                      #   (:77-89 AND :474-486) gain "_cpp_type": None
tests/test_formula_transpiler_cpp.py  # NEW ~44 cases (mirror csharp twin; FieldRef → runtime::v(this->my_field))
tests/cpp_static/                     # NEW CMake + Catch2 project
  ├── CMakeLists.txt                  #   FetchContent Catch2 v3; add ../../static/cpp to include path;
  │                                   #   compiles test TUs only (runtime is header-only)
  └── test_*.cpp                      #   18 files = C#/Java parity (§5 F-map); test_poco_model.cpp = GATE
.clang-format                         # NEW (repo root)
```

### 3.2 Generated output (per run)

```
<output>/
├── dynamic/
│   ├── options/   {options_name}.hpp        (enum class + to_json/from_json)
│   ├── types/     {table}_fields.hpp, {table}_view.hpp, create_{table}_fields.hpp
│   ├── formulas/  {table}_filters.hpp
│   ├── models/    {table}_model.hpp
│   └── tables/    {table}_table.hpp
├── static/                                   copied verbatim from static/cpp/ (incl. vendor/nlohmann/)
└── airtable.hpp                              root entry point
```

Everything `namespace myairtable`, header-only. Consumers: add `<output>` to include path, link
`libcurl`, `#include "airtable.hpp"`.

### 3.3 Test repo (`myairtable-tests`)

```
cpp/
├── CMakeLists.txt                # HAND-WRITTEN: FetchContent Catch2; include_directories(output);
│                                 #   find_package(CURL); one sequential test binary from tests/*.cpp
├── output/                       # regenerated by build.sh (gitignored)
└── tests/
    ├── test_setup.hpp/.cpp       # .env walker, make_airtable(cache_seconds)/bad-key factory,
    │                             #   primary_key(suite,label) → "Cpp {suite} {label} {ms}-{rand}"
    ├── test_harness.cpp          # smoke: kVersion + fixture wiring
    └── test_<scenario>.cpp       # 21 canonical files (§5 F-map) = C#/Java scenario parity
build.sh                          # MOD: --cpp-folder "$AIRTABLE_DIR/cpp/output"
test.sh                           # MOD: usage text; `all` loop += cpp; cpp) dir arm; suite→TEST_CMD block
                                  #   (cmake --build then binary with Catch2 name/tag filters, e.g.
                                  #   ./build/cpp_tests "[crud]"); execute branch
checks.sh                         # MOD: guarded cmake configure+build (compiles output/ against tests/)
                                  #   + clang-format cpp/tests
.gitignore                        # MOD: cpp/output/, cpp/build/
.clang-format                     # NEW (repo root)
```

Suite→tag map (Catch2 tags on every TEST_CASE): `[crud]` struct/orm-table/orm-model/pagination/
error-paths/field-round-trip/upsert-depth · `[json]` serializing · `[filter]` filter/escaping/sort ·
`[runtime]` runtime-formulas ×3 · `[cache]` caching/concurrency.

### 3.4 `formula_transpiler.py` cpp arms — explicit checklist (F8.1)

Each numbered line = an edit site (line numbers from current tree):

1. `"cpp"` in `Language` Literal (:21).
2. `_self` (:324-329): cpp arm → `"this"` (emitted as `this->field` — see 17; the map stores `this`).
3. `_runtime` (:334): cpp → `"runtime"`; **`_rt()` (:336-341) cpp branch emits `runtime::{name}`
   (`::` separator — the one structural novelty vs all prior languages)**.
4. **`_emit_function_call` guard (:501-503)**: add `"cpp"` to the dispatch set → `_rt(name)(args)`
   (CRIT — else every runtime call emits `runtime.NAME`).
5. NumberLiteral (:363-367): cpp arm → `runtime::v({value})` (int vs double form preserved; `.0` kept).
6. StringLiteral (:385-386): cpp arm → `runtime::v({double_quoted})` (C++ string escapes via
   `_cpp_string_literal`).
7. FieldRef (:425-429): cpp arm → `runtime::v(this->my_field)`; **`field_name_map` populated with
   `name_snake()`** (+ `_cpp_ident` escape).
8. `_emit_fn_record_id` (:552): `runtime::v(this->id.value_or(""))`.
9. `_emit_fn_true`/`_false` (:565/:576): `runtime::v(true/false)`.
10. `_emit_fn_blank` bare (:588-592): cpp arm → `runtime::v(nullptr)` (**NOT** the `"null"` default —
    C++ spells it differently; explicit arm required). With arg (:603): `runtime::v(runtime::is_blank({arg}))`
    — a tiny runtime helper beats emitting `({arg}).is_null()` because the arg is already a json value.
11. `_emit_fn_not` (:621): `runtime::v(!runtime::is_truthy({arg}))`.
12. `_emit_fn_and`/`_or` (:641/:676): `runtime::v(is_truthy(a) && is_truthy(b))` / `||`.
13. `_emit_fn_xor` (:804): `runtime::v(is_truthy(l) != is_truthy(r))`.
14. `_emit_fn_if` (:842): `(runtime::is_truthy(c) ? (t) : (f))`; fallback branch `runtime::v(nullptr)`.
15. `_emit_fn_ifs` (:878): result init `runtime::v(nullptr)`; ternary chain.
16. `_emit_fn_switch` (:945/:988): flat-varargs `runtime::SWITCH(expr, runtime::v(nullptr), pairs...)` —
    C++ signature `json SWITCH(const json& expr, const json& dflt, const std::vector<json>& pairs)`?
    No — match the Java/C#/Go flat shape via `std::initializer_list<json>` or variadic pack; decide
    in F2 and keep the transpiler arm in lockstep.
17. Fall-through `None` guards (~20 sites: len/str-methods/encode_url/int/abs/sqrt/exp/log10(→LOG)/
    power/mod/regex_*/min/max/sum/round/concatenate/rept/date_part/datetime_parse): add `"cpp"` to
    each guard set so they dispatch through `_rt()`.
18. `_emit_fn_countall` (:1040): cpp arm with a brace-init array: `runtime::v(runtime::a(std::vector<nlohmann::json>{args}).size())`-shaped (finalize with runtime sig).
19. `_emit_str` (:1232)/`_emit_num` (:1264): cpp falls to the qualified defaults (verify; no bare-call arm).
20. **`_emit_binary_op` equality (:1343-1356)**: cpp gets its **own block** (C# precedent): number →
    `runtime::v(runtime::n(l) == runtime::n(r))`; string → `runtime::v(runtime::s(l) == runtime::s(r))`
    (std::string value equality); mixed → `runtime::v(runtime::is_equal(l, r))` (+ `!` negation).
21. `_emit_binary_op` arithmetic (:1326)/comparison (:1338)/concat `&` (:1431): cpp+`v()` wrapping arms.
22. `_emit_unary_op` (:1447): `runtime::v(-runtime::n(x))` shape.
23. `_cpp_ident` applied to every emitted identifier path.

## 4. Static Runtime Contract (`static/cpp/`, ~36 headers + vendor)

One public type per header, all `namespace myairtable`, all header-only inline.

- `airtable_json.hpp` — includes vendored nlohmann; `using json = nlohmann::json;` alias;
  `adl_serializer<std::optional<T>>`; shared decode helpers.
- `vendor/nlohmann/json.hpp` — vendored single header (pinned release, version noted in a comment).
- `runtime.hpp` + `runtime_{logic,math,string,date,array,regex}.hpp` — coercions
  `v/n/s/a/an/as_v/d/is_truthy/is_equal/is_blank` + ~90 UPPERCASE functions (group counts from C#:
  logic 8, math 21, string 14, date 24, array 4, regex 3 + coercions). `EXP(1.0)` ULP pin if needed.
  `SWITCH` flat-pairs signature (§3.4-16).
- `airtable_date.hpp` — ISO-8601 codec (3-format decode, millis+Z encode), civil-date math,
  moment-token translator, TZif reader (`tz_offset`).
- `vec_or_value.hpp` / `maybe_special_or_error.hpp` — §2.3.4 variant wrappers + adl_serializers.
- `special_number.hpp`, `error_value.hpp`, `airtable_attachment.hpp` (+ thumbnails),
  `airtable_collaborator.hpp`, `airtable_button.hpp`, `airtable_record.hpp`, `sort.hpp`
  (+ `SortDirection`) — plain structs + to/from_json.
- `airtable_exception.hpp` — base + 7 subclasses (§2.3.7); error-envelope decode.
- `airtable_client.hpp` — libcurl RAII (`CurlHandle`), `curl_global_init` via `std::call_once`,
  blocking endpoints, 429+5xx retry + jitter, pagination accumulate, chunk-of-10 batching,
  `url_encode` via `curl_easy_escape`, `returnFieldsByFieldId` everywhere, owns `CacheStore`.
- `cache_store.hpp` — TTL+LRU, `std::mutex` split-lock, offset-page skip, invalidate/invalidate_all.
- `airtable_query.hpp` — filter/sort/fields/maxRecords/view builder → query params.
- `fields.hpp` — dual ID/name field-bag wrapper. `dict_table.hpp` — raw CRUD. `orm_table.hpp` —
  `template <typename M>` typed CRUD (get/get-many/list/create/update/upsert/remove/remove_all).
- `airtable_model.hpp` — CRTP behavior base (§2.3.12).
- `my_airtable_runtime_info.hpp` — version constant.
- Formula DSL (the `_FORMULA_STATIC_FILES` exclusion set): `formulas.hpp` (AND/OR combinators),
  `formula_field.hpp`, `formula_id.hpp`, `formula_text_ops.hpp`, `formula_{text,number,boolean,
  date,single_select,multi_select,lookup,attachments}_field.hpp`.

## 5. Feature Breakdown (→ beads epic `cpp`, 11 features, ~72 tasks)

Mirrors the proven C# structure. Feature-level here; task-level detail lands in beads on approval.

### F1 — Scaffolding & Infrastructure [P0]
Toolchain (`brew install cmake ninja`; verify clang-format probe); `.clang-format` both repos;
`write_to_file.py` Literal+header; `write_to_cpp_file.py` (+unit tests: ident/string/doc escaping,
choice entries); full type wiring (GENERIC_TO_CPP … idempotency guard — §3.1 list); meta.py;
`main.py cpp` + `all --cpp-folder`; `tests/cpp_static/` CMake skeleton; `myairtable-tests/cpp/`
skeleton (CMakeLists + test_setup + harness); build.sh/test.sh/checks.sh (×2) registration;
`.gitignore`; vendored nlohmann pinned; **1.13 PHASE-0 GATE `test_poco_model.cpp`** proving, with
throwaway prototype types (no static/cpp dependency): (a) aggregate + designated-init + empty CRTP
base on the real toolchain; (b) adl_serializer round-trips — `optional<T>`,
`MaybeSpecialOrError<string|double|time_point>`, `VecOrValue<string>`, `VecOrValue<time_point>`,
nested `VecOrValue<MaybeSpecialOrError<string>>`, null-valued computed decode — decode AND encode,
zero registration; (c) duration wire = numeric seconds; (d) snapshot + writable-only payload diff;
(e) TRUE/FALSE macro-collision probe (§2.3.3). **Exit**: `uv run main.py cpp <dir>` runs (empty
generator OK), both CMake projects configure+build, gate green, checks.sh/test.sh cpp sections wired.

### F2 — Static Runtime Core [P0]
Exceptions (7) → sum types + serializers → value carriers → date codec (+ TZif spike) → query →
fields → client (retry/pagination/batching/url-encode spike) → dict table → cache store. Unit tests
alongside each (test_airtable_exception_decoding, test_special_error_decoding, test_value_coercion,
test_date_decoding, test_fields_dual_access, test_cache_store, test_client_* via a FakeTransport
seam — injectable transport function on the client, C# CS11.1 precedent).

### F3 — Minimal Generator → FIRST LIVE INTEGRATION [P0]
`write_options` (enum + to/from_json), `write_field_types`, `write_tables` (dict access), root
`airtable.hpp`; offline generator content tests; **`test_struct_crud_via_table.cpp` live against the
test base** — earliest possible end-to-end proof (generate → compile → live CRUD), the plan's
fail-fast milestone.

### F4 — ORM Models & Model Ops [P1]
`airtable_model.hpp` CRTP base + `write_models` (from_json/to_json, hooks, doc comments) + orm_table;
offline model-shape tests (test_generators.py) + `test_serializable_model`-equivalents in cpp_static;
live `test_orm_crud_via_table.cpp` + `test_orm_crud_via_model.cpp`.

### F5 — Complex Types [P1] — attachments/collaborators/button/selects live (`test_complex_properties.cpp`).
### F6 — Linked Records [P1] — raw ID lists + resolution (`test_linked_records.cpp`).
### F7 — Formula Builder DSL [P1]
Static `formula_*` headers + `write_formula_helpers` + `F` accessor; `test_formula.cpp` (98-case
port); live `test_filter_by_formula.cpp` (18), `test_formula_escaping.cpp`, `test_multi_field_sort.cpp`.

### F8 — Formula Runtime & Transpiler [P1] — the biggest feature
~90 runtime functions group-by-group with `test_airtable_runtime.cpp` ported case-for-case (184);
transpiler cpp arms per §3.4 checklist + `test_formula_transpiler_cpp.py` (~44); generator emits
`evaluate_*()` methods; live `test_runtime_formulas.cpp`, `test_runtime_formula_variety.cpp`
(unicode!), `test_primary_formula_runtime.cpp`.

### F9 — Caching [P2] — client cache policy tests + live `test_caching.cpp`, `test_cache_concurrency.cpp` (std::thread).
### F10 — Serialization & Hardening [P2]
`test_serializing.cpp` (offline 16) + `test_serializing_integration.cpp` (null clears field) +
`test_special_error_deser.cpp`, `test_error_paths.cpp`, `test_field_round_trip.cpp`,
`test_pagination.cpp`, `test_upsert_depth.cpp`; client hardening tests (bad creds, retry policy,
url encoding) in cpp_static.

### F11 — Parity Audit & Polish [P2]
Cross-language diff of every test file inventory (C# 18-file static / 21-file integration lists);
README (both repos); `checks.sh`/`test.sh` full-suite green runs; count parity ±5% on
formula/runtime suites; idiom pass (no C#-isms).

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

| #   | Risk                                                                     | Mitigation                                                                                     |
| --- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| R1  | Designated-init aggregate breaks (base/member edge case)                 | Compile-verified up front; Phase-0 gate re-proves on real shapes; fallback = default-construct + assign |
| R2  | nlohmann adl_serializer for nested template sums                         | Phase-0 gate (b) — nested + time_point + null-computed, decode AND encode                        |
| R3  | libc++ has no chrono tz (VERIFIED absent)                                | Hand-rolled ISO codec + civil math; TZif reader spike early in F2; fallback Hinnant date/tz      |
| R4  | DATETIME_FORMAT moment tokens ≠ strftime                                 | Port token translator from C#/Java; 184-case runtime suite pins behavior                          |
| R5  | UTF-8 vs code-point string semantics                                     | utf8 helpers, code-point counting (Rust/Go precedent); unicode variety integration test           |
| R6  | `std::regex` semantic gaps vs other targets                              | Only 3 REGEX_* functions; port the C# test patterns early in F8; document any divergence          |
| R7  | `and/or/not/xor` alternative tokens; `delete` keyword; TRUE/FALSE macros | `_cpp_ident` covers alt tokens; `remove()` naming (§2.3.12); push_macro guard + gate probe (e)    |
| R8  | Transpiler emits wrong qualifier (`runtime.X`) or misses `::`            | §3.4-3/4 explicit `_rt()` cpp branch; transpiler unit tests assert `runtime::` prefix             |
| R9  | `map_types` idempotency guard omission → stale types                     | §3.1 explicit guard edit + unit test (C# CRIT-2 precedent)                                        |
| R10 | Vendored json.hpp bloats output / version drift                          | Single pinned header + version comment; only `airtable_json.hpp` includes it                      |
| R11 | curl handle thread-safety / global init races                            | Per-request easy handles + `std::call_once`; cache-concurrency test exercises                     |
| R12 | Header-only compile times annoy consumers                                | Bounded (~6-8k lines); single-include choke points; non-goal to optimize in v1                    |
| R13 | `+` in filterByFormula                                                   | `curl_easy_escape` → `%2B` (correct); verify-first live spike (§2.3.9)                            |
| R14 | `std::exp(1.0)` ULP vs Airtable                                          | Verify-first; pin EXP(1.0) if needed (JVM precedent)                                              |
| R15 | Date wire format rejected by Airtable                                    | millis+Z from day one (C# live-caught lesson baked in)                                            |
| R16 | Catch2 ordering/parallelism assumptions wrong                            | Declaration-order + sequential binary verified in F1 harness; distinct PKs regardless             |
| R17 | cmake/ninja not installed (this machine / CI)                            | F1 brew task; `command -v` warn-skip guards both checks.sh                                        |
| R18 | Offset-token list pages cached                                           | Port the C# skip explicitly; cache unit test covers                                               |
| R19 | int vs double json storage breaks number formatting/equality             | `n()` coerces both; `s()` ports the number-format logic; tests use 42.0                           |
| R20 | GCC/MSVC portability of aggregate+CRTP idiom                             | Only clang is CI-gated (non-goal); idiom is standard C++20; note in README                        |

## 8. Exit Criteria (Full Parity)

- [ ] `uv run main.py cpp <folder>` generates a compiling C++20 header set (`cmake --build` clean).
- [ ] `uv run main.py all --cpp-folder=…` works alongside the other nine languages.
- [ ] `./checks.sh` (myairtable) green with the C++ block included.
- [ ] `./test.sh all` / `./test.sh cpp --all` (myairtable-tests) green — ten languages.
- [ ] All 21 canonical integration scenario files green (C#/Java scenario matrix, snake_case names).
- [ ] Unit parity: 18 cpp_static files ≈ C# inventory; `test_airtable_runtime.cpp` = 184 cases;
      `test_formula.cpp` = 98; transpiler suite ~44; generator content tests ~30.
- [ ] Upsert + dual ID/name Fields access + DX helpers (require_id/value()/values()) tested.
- [ ] Generated code is idiomatic C++20: aggregates + designated initializers, `std::optional`,
      snake_case, header-only, RAII, no Java/C#-isms, clang-format clean.
