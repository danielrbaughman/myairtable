# Swift Target Handoff — F8 in progress

Checkpoint handoff from previous Claude instance. Read this first, then the plan at `.beads/swift-plan-v2.md` and the Swift design memory at `~/.claude/projects/-Users-daniel-Source-rogo-myairtable/memory/project_swift_design_decisions.md`.

## Where we are

**Features F1–F7 complete. F8 (formula runtime transpilation) is partially done.**

### Completed features

| Feature                                     | Status               | Beads epic     |
| ------------------------------------------- | -------------------- | -------------- |
| F1 Scaffolding + `@Observable`+Codable gate | Closed               | myairtable-bt2 |
| F2 Static runtime core                      | Closed               | myairtable-798 |
| F3 Minimal generator (dict)                 | Closed               | myairtable-02u |
| F4 ORM models + offline serialization       | Closed               | myairtable-3yo |
| F5 Complex field types                      | Closed               | myairtable-62r |
| F6 Linked records                           | Closed               | myairtable-1j9 |
| F7 Formula builders (filter DSL)            | Closed               | myairtable-tgm |
| **F8 Formula runtime transpilation**        | **Partial**          | myairtable-i74 |
| F9 Caching                                  | Open, ready          | myairtable-a9y |
| F10 Network serialization tests             | Open, ready          | myairtable-jd3 |
| F11 Parity audit                            | Blocked on F8/F9/F10 | myairtable-3cj |

### Test totals (all passing)

- Static runtime unit tests: **207** across 20 suites
- Generator pytest: **39**
- Integration (live Airtable): **39** across 7 suites
- **Total: 285** tests, all green

## F8 status — what's done, what's left

### Done

- **F8.1** `swift` added to `Language` literal in `src/formulas/formula_transpiler.py:21`
- **F8.2** `_swift_ident()` helper (lives in `src/utils/write_to_swift_file.py` from F1 scaffolding; used via `field.name_camel()` pipeline)
- **F8.3–F8.9** `static/swift/AirtableRuntime.swift` — ~600 lines, 78 functions:
  - Coercion: `N/S/A/AN/AS/D` (6)
  - Math: `SUM/AVERAGE/MIN/MAX/COUNT/COUNTA/ROUND/ROUNDUP/ROUNDDOWN/CEILING/FLOOR/LOG/EVEN/ODD/VALUE/POWER/MOD/ABS/EXP/SQRT/INT` (21)
  - Logic: `IF/SWITCH/BLANK/TRUE/FALSE/ISERROR/ERROR/isTruthy` (8)
  - String: `LEN/LEFT/RIGHT/MID/FIND/SEARCH/SUBSTITUTE/REPLACE/LOWER/UPPER/TRIM/REPT/CONCATENATE/ENCODE_URL_COMPONENT/T` (15)
  - Date: `NOW/TODAY/YEAR/MONTH/DAY/HOUR/MINUTE/SECOND/WEEKDAY/DATETIME_DIFF/DATEADD/IS_SAME/IS_BEFORE/IS_AFTER/DATETIME_FORMAT/DATESTR/TIMESTR/DATETIME_PARSE` (19)
  - Array: `ARRAYJOIN/ARRAYUNIQUE/ARRAYCOMPACT/ARRAYFLATTEN` (4)
  - Regex: `REGEX_EXTRACT/REGEX_MATCH/REGEX_REPLACE` (3)

  All functions take and return `AirtableJSONValue`. Variadic-args functions use `AirtableJSONValue?...`.

- **F8.12 (partial)** `tests/swift_static/Tests/MyAirtableStaticTests/TestAirtableRuntime.swift` — 86 unit tests across 7 suites exercising core semantics. Rust equivalent has ~180 tests; we cover the essentials. Closing the gap to parity is a stretch goal, not a blocker for F8.13.

### Remaining for F8 complete

1. **F8.10** `myairtable-lrn1` — Generator: emit `evaluate()` method on formula fields.
   - For each formula field in a `{Table}Model`, add an async method that calls `AirtableRuntime.*` with the correct formula expression.
   - This is wired through `src/formulas/formula_transpiler.py::transpile_table_formulas()` which the generator calls.
   - Look at how Rust does this in `src/generators/rust.py` (search for `transpile_table_formulas` / `evaluate_formulas_at_runtime`) for the shape.

2. **The Swift branches throughout `src/formulas/formula_transpiler.py`** — THE BIG REMAINING PIECE.
   - The transpiler's `CodeEmitter` has ~95 `if self.language == "rust"` / `"python"` / `"typescript"` branches that produce language-specific code.
   - Each needs a `"swift"` branch. Swift emission will be similar in shape to Rust (both typed, both runtime-backed).
   - Key places to branch (grep for `"rust"`):
     - Field reference emission (lines 296, 301, 329)
     - Boolean / nil literals (lines 391, 433, 438, 443, 449, 453, 461, 468, 473, 482)
     - Function-call emission (lots throughout)
     - Variadic / optional parameter handling (Rust has special cases — Swift should behave the same since types are similar)
   - Swift emission style:
     - `AirtableRuntime.SUM(...)` (not bare `SUM(...)`)
     - Field refs: `self.fieldName` (matches Rust's `self.field_name`)
     - Nil: `nil` (not `None`/`null`)
     - Boolean: `true` / `false`
   - The Rust branches are the best reference. Swift differs mainly in:
     - Optional chaining: `?` not `.unwrap()`
     - `Darwin` math functions (`pow`, `log`, etc. — already used in AirtableRuntime.swift)
     - `AirtableJSONValue` instead of `serde_json::Value`

3. **F8.11** `myairtable-bi2h` — Python unit tests in `tests/test_formula_transpiler_swift.py`.
   - Mirror `tests/test_formula_transpiler.py` (which tests Python/TS/JS/Rust emission).
   - Assertions: given a formula AST, assert the Swift emission matches expected strings.

4. **F8.13** `myairtable-xjne` — Integration test `myairtable-tests/swift/Tests/MyAirtableTests/TestRuntimeFormulas.swift`.
   - Parity with `rust/tests/test_runtime_formulas.rs`.
   - Create a record with known input values, fetch server-side formula results, verify Swift's runtime evaluation matches.

## Critical design decisions already locked in

See `memory/project_swift_design_decisions.md` for the complete list. The ones most relevant to F8:

- **`AirtableJSONValue`** is the value type for the runtime (defined in `static/swift/Types.swift`). It's a Codable/Sendable enum with cases `null/bool/int/double/string/array/object`.
- **`AirtableRuntime`** is a `public enum` (namespace, not instantiable) with static methods.
- **Dirty tracking** on models uses an explicit snapshot dict (`_snapshot: [String: AirtableJSONValue]`), NOT `@Observable` tracking. The runtime's `toRecord()` produces this dict via JSON round-trip.
- **`_attachedClient`** on each model is how model-side `fetch()/save()/delete()` work without taking a table argument. OrmTable's decode path sets it.
- **Field-level formula filter accessor**: `PrimaryModel.f.fieldName.equals(...)` (lowercase `.f`), not `.filters` or `.F`.
- **`typecast` parameter**: deliberately NOT exposed on Swift (matches Rust/Py/TS). Cross-target typecast support tracked at `myairtable-hbph`.
- **OrmTable and DictTable API**: overloaded `get/create/update/delete` (no `One`/`Many` suffix). Batch variants chunk by 10. ORM methods forward directly on `{Table}Table` (no `.orm` accessor).
- **`AirtableQuery` fluent builders**: no `with` prefix. `query.formula(...)` / `.sort(...)` / `.maxRecords(...)` etc.
- **Package.swift**: generator does NOT emit. Test repo has a hand-written one at `myairtable-tests/swift/Package.swift`.

## Commit cadence preference

User wants **a git commit after every beads task closed** — not batched at feature boundaries. See `memory/feedback_commit_cadence.md`. Each task = 1 commit.

## File locations

### Main repo: `/Users/daniel/Source/rogo/myairtable/`

- Generator: `src/generators/swift.py`
- Formula transpiler (needs Swift branches!): `src/formulas/formula_transpiler.py`
- WriteToSwiftFile helper: `src/utils/write_to_swift_file.py`
- Type mapper: `src/utils/type_mapper.py` (GENERIC_TO_SWIFT, LanguageConfig for swift)
- Static runtime: `static/swift/` — 12 files, ~2000 lines total
  - `AirtableRuntime.swift` (600 lines, new in F8)
  - `Formula.swift` (350 lines, F7)
  - plus AirtableClient / AirtableError / AirtableModel / AirtableQuery / CacheStore / DictTable / Fields / Formula / LinkedRecord / OrmTable / Placeholder / Types
- Pytest generator tests: `tests/test_generators.py` (39 cases)
- Static Swift tests: `tests/swift_static/Tests/MyAirtableStaticTests/` (207 tests)
- Plan document: `.beads/swift-plan-v2.md`

### Test repo: `/Users/daniel/Source/rogo/myairtable-tests/`

- Swift package: `swift/` (Package.swift + Tests/ checked in; `output/` regenerated)
- Integration tests: `swift/Tests/MyAirtableTests/` (7 files, 39 tests):
  - TestSetup.swift (env loading)
  - TestStructCrudViaTable.swift (dict CRUD)
  - TestOrmCrudViaTable.swift
  - TestOrmCrudViaModel.swift
  - TestSerializing.swift (offline)
  - TestComplexProperties.swift (attachments/users/computed/button)
  - TestLinkedRecords.swift
  - TestFilterByFormula.swift
- Pending: `TestRuntimeFormulas.swift` (F8.13)

## How to run things

```bash
# Regenerate Swift from Airtable schema (both repos involved):
cd /Users/daniel/Source/rogo/myairtable-tests
./build.sh

# Static runtime tests (myairtable repo):
cd /Users/daniel/Source/rogo/myairtable/tests/swift_static
swift test

# Integration tests against live Airtable:
cd /Users/daniel/Source/rogo/myairtable-tests
swift test --package-path swift

# Pytest:
cd /Users/daniel/Source/rogo/myairtable
uv run pytest tests/test_generators.py

# Full checks (both repos have their own checks.sh):
./checks.sh    # run from each repo root
```

## Known gotchas

1. **SourceKit lag** — after regenerating Swift, the IDE diagnostics may show errors for a few seconds. `swift build` is the authoritative answer.
2. **Property/method name collision on `AirtableQuery`** — stored properties share names with fluent methods (`formula`, `sort`, `fields`, etc.). If a caller has a local var with the same name, Swift's overload resolution picks the property and fails with "cannot call value of non-function type". Rename the local var.
3. **Alphabetical init param order in `Create{Table}Model`** — generator emits params in alphabetical order; call sites must respect that ordering.
4. **Pre-commit hook runs `./checks.sh`** — commits can take up to a minute as it runs lint + tests across all 5 languages. If a commit seems to hang, it's running checks.
5. **Model is non-Sendable** (`@Observable` class) — this means `get([String])` is sequential, not parallel (can't cross task-group boundaries).
6. **`AirtableRuntime.SWITCH`** has `cases:` labeled arg (Swift keyword conflict with `switch`). Direct-call: `AirtableRuntime.SWITCH(expr, cases: [(.int(1), .string("one"))])`.

## Beads workflow reminder

- Use `bd` for ALL tracking (NOT TodoWrite/TaskCreate/markdown).
- Mark tasks `in_progress` when starting, `close` with a reason when done.
- Session close: `git status` → `git add` → `bd sync` → `git commit` → `bd sync` → `git push`.

## Next steps (suggested order)

1. **Start with the `formula_transpiler.py` Swift branches** — this is the largest and most impactful remaining work. Without it, formulas won't transpile to Swift code at all.
2. Then **F8.10** (generator emits `evaluate()` methods) — small change, depends on the transpiler working.
3. Then **F8.11** (Python unit tests for Swift emission).
4. Then **F8.13** (integration test `TestRuntimeFormulas.swift`).
5. Close F8 feature, move to F9 (Caching — populate `CacheStore` actor, wire it into `AirtableClient`), F10 (network serialization tests), F11 (parity audit).

Good luck. 🤝
