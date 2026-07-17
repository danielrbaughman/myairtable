# Handoff — publishing epic (myairtable-cozj)

_Written 2026-07-16 at the end of a long session. Run `bd show myairtable-cozj` first;
every issue carries its own detail. This doc is the stuff that ISN'T in the issues:
what's in flight, what will waste your time, and which "obvious" checks are lies._

## Where things stand

**Goal:** myairtable becomes a dedicated code-generation app on Airtable's *public* API,
published to PyPI, with its 28 MCP tools relocated to `../rogo-mcp` so the whole team gets
them.

Epic **myairtable-cozj** — 5/10 complete.

| Issue | Phase | State |
|---|---|---|
| `myairtable-4d4f` | Phase 0 — static paths resolve from the module, not cwd | ✅ merged (#29) |
| `myairtable-dwbj` | Phase 1a — `src/*` → `src/myairtable/*` (215 imports) | ✅ merged (#30) |
| `myairtable-1mcd` | Phase 1b — `static/` → `src/myairtable/static/` (6 build systems) | ✅ merged (#31) |
| `myairtable-d2mh` | Phase 2 — packaging metadata, extras, dep hygiene | ✅ merged (#32) |
| `myairtable-r7c9` | Phase 3a — base registry, delete `AirtableCredentials` | ✅ **PR #33 OPEN** |
| `myairtable-2ptk` | Phase 3b — thread `base=` through the 28 tools | ⬜ **NEXT, unblocked** |
| `myairtable-8oig` | Phase 4 — publish to PyPI | ⬜ blocked by 3b |
| `myairtable-vmj4` | Phase 5 — consumers → published pkg; tools → rogo-mcp | ⬜ blocked by 4 |
| `myairtable-rm5o` | Decouple verbose from typer (gets typer out of core) | ⬜ P2 |
| `myairtable-uzzc` | Version stamp in generated headers | ⬜ P2 |

**Start here:** PR #33 needs review/merge. Then `myairtable-2ptk`.

## Repo state at handoff

| Repo | Branch | State |
|---|---|---|
| `myairtable` | `feat/explicit-base-id` | clean, pushed, **PR #33 open** |
| `myairtable-tests` | `main` | clean |
| `airtable` | `master` | clean (restored — I generate into it to test; always restore) |
| `rogo-mcp` | `master` | **DIRTY — not mine, see below** |

### rogo-mcp has in-flight work that is NOT from this session

```
 M src/crossrepo_tools.py     <- someone is fixing rogo-mcp-suw
?? tests/test_crossrepo.py    <- new test for it
M  .beads/issues.jsonl        <- contains rogo-mcp-suw; uncommitted
```

I filed **`rogo-mcp-suw`** (in rogo-mcp's own beads, not myairtable's): `airtable_field_search`
is broken — `FIELDS_CSV` points at `../airtable/schema/fields.csv`, a path that predates the
multi-base split (the CSVs are now `schema/{crm,equipment,fieldstats}/fields.csv`). Every call
raises `FileNotFoundError`. Local-only: the tool has no `tags={"remote"}` so `apply_mode`
excludes it from the deployed server.

Someone has started the fix (globbing per base — matches the issue's recommendation). **Don't
redo it.** The `.beads/issues.jsonl` there is uncommitted, so `rogo-mcp-suw` lives only in the
local Dolt DB until someone commits/pushes it.

## Things that will waste your time if you don't know them

### 1. `git checkout main && git pull` silently leaves you on stale main

Bit me twice. `bd` operations dirty `.beads/issues.jsonl`; the `&&`-chained `pull` then fails
with "Please commit or stash", but the `checkout` already succeeded — so you're on main,
*unpulled*, and any branch you cut is based on the wrong commit. I nearly started Phase 1b on
pre-Phase-1a code.

```bash
git checkout main && git checkout -- .beads/issues.jsonl && git fetch -q origin && git reset --hard -q origin/main
```

Always confirm the base commit before branching.

### 2. `bd` exports on a COMMIT HOOK — chicken-and-egg

Updating issues without touching code produces nothing to commit, so the hook never fires, so
`issues.jsonl` never updates. Run `bd export` explicitly (it dumps all ~800 issues to stdout —
noisy, harmless).

### 3. "Regenerate and check `git status` is empty" is a LIE in `../airtable`

Its committed output is a **snapshot of a live base**, taken whenever someone last ran
`generate.sh`. The base drifts underneath it (I saw `Total Fields 2167 → 2168`,
`Last Updated 2026-07-13`). A clean regen showed **3511 diffs** that had nothing to do with my
change.

**The only valid gate is an A/B against `main`:** generate all three bases with main → snapshot;
same with your branch → snapshot; `diff -r`. Recipe at the bottom.

Also: `generate.sh` starts with `git fetch && git pull` on myairtable, so it **cannot run from a
feature branch** (no upstream → `set -e` → exit 1 before generating anything). An empty
`git status` then means *nothing ran*, not success. Replicate its `build_base` calls directly.
(Phase 5's uvx migration removes this.)

### 4. `myairtable-tests` uses ONE base — it structurally cannot catch base-selection bugs

`./build.sh` regenerates all 10 language targets against a single base. Byte-identical output
there is a great no-op proof for renames/packaging, and it has caught real bugs. It proves
**nothing** about which base got selected. That needs the 3-base A/B.

`./test.sh py` runs 286 live tests. A raw `build.sh` always leaves `rust/output/dynamic/` dirty
(19 files, import ordering) — **pre-existing**, `checks.sh:22` runs `cargo fmt` after generation
so committed Rust is post-format. Don't chase it.

### 5. The generated-code string trap — bitten twice, nearly a third time

Generators emit *strings* that look like our code but resolve against the **generated** package:

- `generators/python.py` — `get_api_key`/`get_base_id` → generated `static/helpers.py`
- `generators/cpp.py` — `include_local("static/...")` → the **output's** `static/`, not ours

Rewriting either breaks every generated package. Before any sweep, check whether the match is
inside `write.line_indented(...)` / an f-string.

### 6. BSD sed on macOS has no `\b`

My import-rewrite sed silently matched nothing. Use `perl -pi -e`. And watch double
substitution — two rules both matching produced `src/myairtable/src/myairtable/`.

### 7. Empty files break git rename detection

Moves of 0-byte `__init__.py` files show as bare `D`/`A` with nonsensical pairings. Don't panic —
prove nothing was lost by comparing tracked file *sets*:

```bash
git ls-tree -r --name-only main | sort > /tmp/a
git ls-files | sort > /tmp/b
comm -23 /tmp/a /tmp/b   # only on main
comm -13 /tmp/a /tmp/b   # only on branch
```

### 8. The Bash safety classifier flaps

"claude-sonnet-5[1m] is temporarily unavailable" — retry, it comes back. Read-only tools keep
working. Don't chain `sleep` to wait it out (blocked).

## Architecture facts worth not re-deriving

- **The pipeline:** `myairtable` (generator) → `airtable` repo (generated py/rs/ts for **3
  bases**: crm, equipment, fieldstats) → `rogo-mcp` (pins `airtable@v3.46.38` *and* reads its
  generated `schema/*/fields.csv`). Three edges into codegen output.
- **`schema_tools` is a veneer over the codegen engine**, not a peer. It imports `formulas/*`,
  `generators/mermaid`, `meta`. Arrow points one way; codegen never imports it. That's why
  publishing myairtable-as-a-library is the only way to move the tools.
- **Root `main.py` is a transitional shim.** `generate.sh:24` and `build.sh:12` both invoke
  `uv run main.py`. It re-exports `myairtable.main:main`. Phase 5 deletes it.
- **`typer` is in core** via `typer-verbose` → `typer>=0.20.0`, because `meta.py:27` imports
  `utils/verbose` at module level. Known, documented in pyproject. `myairtable-rm5o` fixes it.
- **`rich` was undeclared** despite 15 importers — it only resolved via typer's transitive pull.
  Now declared. This becomes load-bearing the moment `rm5o` lands.
- **`dateparser` belongs to the generated runtime**, not myairtable. `../airtable` declares it
  correctly. It's in myairtable's dev group only because our tests exercise the bundled runtime.

## The removed internal API

Deleted in `7abb30c` (`myairtable-cw26`) — 2,458 lines + a 1,401-line endpoint doc. Superseded by
[`airtable-user-mcp`](https://github.com/Automations-Project/VSCode-Airtable-Formula) (npm, MIT,
66 tools on the same v0.3 endpoints, Patchright auth, OS keychain, tool profiles) plus the
official Airtable MCP's `list_pages_for_base`.

Only `list_automations` and `audit_shares` were unique. **If you ever want them back**, the
material is at `eaa565b`:

```bash
git show eaa565b:src/internal_api/tools.py
git show eaa565b:docs/airtable-internal-api.md   # the endpoint reference — the valuable part
```

Leftover on disk: `~/.myairtable/internal-session.json` holds Airtable session cookies for the
removed feature, and `AIRTABLE_EMAIL`/`AIRTABLE_PASSWORD` linger in `.env`. Nothing reads them.
Worth deleting.

## Next: Phase 3b (`myairtable-2ptk`)

Read the issue — it has the full design. The traps, in order of how badly they bite:

1. **The fan-out.** `base_health_report` calls **8** other tools plus its own `_get_base()`;
   `dependency_graph_metrics` and `reverse_dependencies` each call two. Miss one and
   `base_health_report(base="equipment")` returns **crm's** findings with no error — the worst
   failure mode for an agent-facing tool. A signature audit cannot catch this; only a
   call-graph test (stub `_get_base` to *raise* unless called with the requested key).
2. **Byte-identical proves nothing here** — 3b touches no code generation reaches. Replace it
   with a golden snapshot of the MCP tool schema (all 28: name/params/defaults/required/
   description). That IS the artifact consumers bind to.
3. **~11 test stubs, not 3.** `_stub_public_finders` (`test_schema_analysis.py:171-184`) has 8
   zero-arg lambdas; plus 3 `_get_base` stubs.
4. **Docstrings are MCP tool descriptions.** ONE identical `Args:` line. Never touch the summary
   line — tool selection ranks on it.
5. `mcp_server.py:14` says **"Provides 24 tools"**; there are 28. Fix while you're there.

The design is settled (decided with the user after a 3-subagent critique):

- **Alias registry, not a bare `base_id`.** A raw base id is not discoverable — rogo-mcp has one
  `AIRTABLE_BASE_ID` (crm), the others live only in `../airtable/.env`, and myairtable has no
  `list_bases`. A bare param would be **unpopulatable**. 3a already shipped
  `configure_bases()`/`resolve_base()`; 3b just threads `base=` through.
- Keyword-only `*, base: str = ""`. `""` not `None` (FastMCP renders `str|None` as
  `anyOf:[string,null]`, which agents handle worse). Verify FastMCP schema-generates kw-only
  params before committing to it.
- Cache key must be `(base_id, api_key)` — base_id alone is a cross-credential leak.

## Verification recipes

**The 3-base A/B gate** (the only thing that catches base-selection bugs):

```bash
# 1. baseline on main
cd ~/Source/rogo/myairtable && git stash
# 2. run the build_base calls from ../airtable/generate.sh directly (NOT generate.sh —
#    its git pull fails on a feature branch). Add --no-svg to skip slow SVG rendering.
# 3. snapshot ../airtable/{schema,py,ts,rs,docs} -> /tmp/base3
# 4. git stash pop; regenerate; snapshot -> /tmp/br3
diff -r /tmp/base3 /tmp/br3        # expect identical (6736 files)
cd ~/Source/rogo/airtable && git checkout -- . && git clean -fd   # ALWAYS restore
```

**The 10-language no-op proof** (renames/packaging):

```bash
cd ~/Source/rogo/myairtable-tests && ./build.sh    # snapshot */output, diff vs main-generated
```

**Everything else:** `./checks.sh` (exits 0; Rust 276, Swift 274, C# 400, C++ 480, Go, Kotlin+Java,
Python 1168). Swift's `Executed 0 tests` line is XCTest reporting zero XCTest cases — the suite
uses swift-testing (`Test run with 274 tests`). Not a regression; main prints it too.

**Wheel acceptance** (Phase 2's, still worth re-running before Phase 4):

```bash
uv build && uv venv /tmp/v && uv pip install --python /tmp/v/bin/python "dist/*.whl[cli]"
cd /tmp && /tmp/v/bin/myairtable --base-id X --api-key Y py /tmp/out   # must byte-match a repo run
```

## Live test base — read before running the suite

`myairtable-tests` runs against a **live shared base**. `myairtable-1yg7` documents orphan debris
from crashed runs. I deleted 5 `Filter Test` orphans (2026-07-01) **with the user's explicit
sign-off** — that issue itself says "deletion of shared-base records needs human sign-off". Do
the same; don't delete live records unilaterally.

Still listed as untouched debris: `JavaScript Pagination Record 1782405968052-*`, `Mutation Test`,
`CacheConc`, `Probe BadField`, `ErrJS`. Python is green (286/286) so they don't break py; they may
break js/ts. The durable fix is a pre-run sweep fixture — the fixture currently deletes only what
it created, so any interrupted run poisons the next one permanently.

## Working agreements from this session

- **One PR at a time**, each independently verifiable. Land, merge, then start the next.
- **Pure-no-op PRs are proven by byte-identical output.** Anything that would break that property
  gets split out (that's why `rm5o` and `uzzc` exist as separate issues).
- The user reviews and merges; I don't merge my own PRs.
- Deleting live data or pushing to Rogo-owned repos → **ask first**.
