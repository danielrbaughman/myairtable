# Integration test coverage expansion — plan

Epic: **myairtable-upgs**
Branch: `test-coverage-expansion` (both `myairtable` and `myairtable-tests`).
Plan status: approved 2026-06-25. No code yet — execute one child at a time.

## Context

`../myairtable-tests` runs live-Airtable integration tests against the generated
client, mirrored across 9 targets (ts, js, py, rs, swift, kotlin, java, go, cs).
Existing suites: crud (struct/dict, orm-via-table, orm-via-model, interface),
serializing (+ integration), filter-by-formula, runtime-formulas, caching,
complex-properties, linked-records, special-error-deser.

This epic closes gaps found by auditing the generated `client`/`query` code
against all 9 suites — capabilities the generated code supports but no test
exercises.

## Execution model

1. **One child at a time**, in priority order (see below).
2. For each child: implement in **C# first** (most complete reference suite),
   get it green against the live base, then **port across the other 8 suites**.
   Wire any new suite filename into `test.sh` (per-language `--suite` cases).
3. Run `./test.sh <lang> <suite>` then `./test.sh all` before closing.
4. **Fixes along the way**: if a test reveals a real bug in the generated code
   or transpiler (in `myairtable`), open a `bug` bead, mark it `blocks` the child
   test bead, fix it, regenerate, then close both.
5. Commit after each child (per commit-cadence memory). Both repos.

## Children & suggested order

| #    | Bead            | Pri | One-liner                                                                    |
| ---- | --------------- | --- | ---------------------------------------------------------------------------- |
| TC1  | myairtable-4kp3 | P1  | Multi-page pagination — list >100 records via offset loop                    |
| TC2  | myairtable-4ecx | P1  | Formula-value escaping — `'` `"` `\` newline, unicode/emoji in filter values |
| TC3  | myairtable-cszk | P1  | Error/validation paths — 422/404/401, typed exceptions (not ThrowsAny)       |
| TC4  | myairtable-qg0r | P1  | Runtime-formula input variety — incl. dead `IF(OR(=BLANK()))` branch         |
| TC5  | myairtable-nggd | P2  | `WithPageSize` + pageSize×maxRecords (depends on TC1)                        |
| TC6  | myairtable-oi85 | P2  | Primary Complex/Nested formulas evaluated at runtime                         |
| TC7  | myairtable-tywg | P2  | Field-type round-trip completeness via re-fetch                              |
| TC8  | myairtable-i9jf | P3  | 429 retry/backoff (stub server / low-delay seam)                             |
| TC9  | myairtable-ux0l | P3  | Concurrency / cache thread-safety                                            |
| TC10 | myairtable-1ehw | P3  | Upsert depth — multi-record, multi-key, multi-match                          |
| TC11 | myairtable-35u2 | P3  | Multi-field sort + sort-with-filter                                          |

Rationale for the top 4: untested non-trivial code paths (pagination loop,
formula escaping, transpiler BLANK branch) and a likely-real escaping bug.

## Risk notes

- **TC2** and **TC4** are the most likely to surface real bugs (formula
  string escaping; transpiler BLANK/edge-case handling) → expect fix beads.
- **TC8** (retry) and **TC9** (concurrency) may need a test-only client seam and
  are inherently less portable; acceptable to cover a subset of languages and
  note the gap rather than force all 9.
- All live tests must keep per-run unique keys + best-effort cleanup to stay
  parallel-safe against the shared base.
