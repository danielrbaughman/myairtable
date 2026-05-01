# Internal API — Feature Options & Groundwork

Discussion notes from 2026-05-01. Companion to `docs/airtable-internal-api.md`
(which is the authoritative endpoint reference). This doc is the _menu_ — what
we could build, what each thing needs, and where to start.

## Codebase grounding (so future-you doesn't re-derive it)

**myAirtable today** runs on the public meta API only
(`api.airtable.com/v0/meta/bases/{base_id}/tables`) via httpx, PAT-scoped,
single-binary, CI-safe.

- `src/meta.py` — Pydantic `Base`/`Table`/`Field`/`View`/`Choice`/`Options`
  models built from that response. `View` carries only `{id, name, type,
table_id}` — no live filter/sort/group state.
- `src/generators/` — `csv | python | typescript | javascript | rust |
markdown | html | mermaid`.
- `src/formulas/` — `tokenizer | formatter | flattener | sanitizer | condenser
| highlighter | transpiler`.
- `mcp_server.py` — 24 read-only MCP tools (schema browsing, dependency
  tracing, formula analysis, validation, statistics, Mermaid diagrams).

**Reference implementation** (`vscode-airtable-formula/packages/mcp-server/src/`):

- `auth.js` (568 lines) — Patchright persistent context, CSRF + per-appId
  `secretSocketId` capture (LRU 50, never shared across bases), bounded
  request queue (default 64, concurrency 1), 15s per-`page.evaluate`, 30s
  wall-clock budget, 401/403 → recovery, 429/503 → exp backoff (max 3).
- `client.js` (1883 lines) — every endpoint plus the sharp-edge workarounds:
  filter operator normalization (`is`→`=`, `isAnyOf` collapse), type-aware
  emptiness rewrite for text/formula/lookup/rollup, foreignKey emptiness
  hard-fail with helper-formula advice, partial-fieldOrder merge, batched
  `setViewColumns` (hide-all → show-set → move at visible index 1, since
  primary is pinned at 0), two-step delete with summarized dependency graph,
  `expectedName` safety on every destroy.
- `tool-config.js` — tool categories: `read`, `*-write`, `*-destructive`,
  `view-section*`, `form-write`, `extension`. Profile-based gating.

## What the internal API actually unlocks

Four buckets — every feature falls into exactly one:

1. **Live view state** — filters, sorts, grouping, column order/visibility,
   frozen count, color config, row height. Public meta API gives `{id, name,
type}` and stops. Most immediately visible value: views named "Active"
   or "Q2 Review" tell readers nothing without their filter expressions.
2. **Authoritative analysis** — formula validation
   (`getUnsavedColumnConfigResultType`) and dependency graph
   (`column/destroy` precheck). Airtable's own parsers and reachability,
   returned as JSON.
3. **Schema mutations** — create/rename/delete tables/fields/views, plus
   `updateConfig` on the things the public REST API explicitly can't write:
   formula text, lookup/rollup config, view filters, descriptions. The
   transformative bucket.
4. **UI affordances no API exposes at all** — view sections (sidebar
   grouping), bulk select-option rename, Kanban/Gallery cover, calendar
   columns, form metadata, extensions.

## Read-side features that pay back fast

- **Live view state in HTML/MD docs.** Render each view's filter expression
  (formatter + highlighter exist), sort order, grouping, visible columns.
  `html.py` already has the rendering primitives.
- **Sidebar sections in docs.** `viewSectionsById` + `viewOrder` group views
  the way Airtable's sidebar does; current docs render a flat list.
- **Typed view constants in codegen.** `Contacts.views.active.filter_formula`
  visible to the type system instead of a string view name. `.get(view=...)`
  can default `fields=[...]` to the view's visible columns.
- **Transpiler regression test via `validateFormula`.** Run every formula
  through Airtable's validator, compare reported `resultType` against our
  static inference. Divergence = either transpiler bug or an edge worth
  knowing about. Free signal, runs nightly.
- **Dependency-graph reconciliation.** Cross-check `find_dead_fields` /
  `trace_field_dependencies` / `find_circular_references` against the
  destroy-precheck graph. Either we find parser bugs or we discover
  lookup/rollup edges text-parsing misses.
- **New MCP tools paired with existing ones:** `validate_formula`,
  `get_view` (full state), `get_view_sections`, `get_field_dependencies`.

## Write-side features, ordered by ambition

- **Description sync.** Push the rich descriptions our markdown docs already
  contain back into Airtable. One endpoint, tiny blast radius — the
  sensible first-write feature.
- **Bulk choice rename.** CSV-driven `updateFieldConfig` for singleSelect /
  multiSelect choices. Same CSV-name-locking pattern, applied to choices.
- **Formula refactoring CLI.** Pairs the existing transpile/format/flatten/
  sanitize stack with `validateFormula` + `updateFieldConfig`:
  - `myairtable formula format-all`
  - `myairtable formula rename-field fldX "New Name"` (rewrites every
    consumer's formula)
  - `myairtable formula inline fldHelper` (flatten into consumers, then
    delete the helper)
    Niche but uniquely valuable — nothing else does this.
- **`myairtable push`.** Code-as-source-of-truth. Diff a Python spec against
  the live base, plan-only first, apply via the schema-mutation endpoints.
  Closes the loop on CSV-driven property names. The biggest leap, both
  technically (diff + planner + ordering) and in blast radius.

## Groundwork, by what gates what

- **Everything needs:** Python port of `auth.js` — Playwright extra,
  persistent Chromium profile, `myairtable login` subcommand, CSRF +
  per-base `secretSocketId` capture, request queue, recovery/backoff.
  ~700 lines of mechanical translation. The gate. Probably ships as an
  optional install extra (`myairtable[internal]`) so the existing CI/PAT
  path keeps working unchanged.
- **Read enrichment also needs:** typed wrappers around `getApplicationData`
  - `readTableData`, plus a way to attach live state onto the existing
    `Base`/`View` models without forcing every caller through the internal
    path. Probably an opt-in `Base(internal=True)` or a sibling `LiveBase`.
- **Validator + dep-graph cross-check needs:** auth port + two endpoints
  - a pytest harness. Cheapest non-trivial use of the internal API and the
    one that gives permanent regression coverage for free.
- **Any write feature needs:** `_mutationParams` envelope helper,
  error-shape parsers (`FAILED_STATE_CHECK`,
  `SCHEMA_DEPENDENCIES_VALIDATION_FAILED`), filter-normalization helpers
  if we ever touch view filters, and a throwaway test base. CI can't run
  the auth — write-side tests are local-only.
- **Push specifically needs:** a normalized schema diff (Operation list),
  a planner that orders creates-before-references and destroys-after, plus
  a way to express the "desired" side. Decorators on generated code are
  brittle under user edits — a small declarative DSL is more honest.

## Two natural starting points

Both share the auth port; the real first decision is _"is the auth port
worth standing up?"_ Once it's there, either of these is days of work.

1. **Read-only enrichment.** Auth port + read endpoints + live view state
   in `html.py`/`markdown.py`. Highest visible-value-per-line; HTML doc-site
   already has the rendering primitives.
2. **Validator + dep-graph cross-check.** Auth port + two endpoints + a
   test harness. No user-facing feature, but a permanent transpiler
   regression test and a free dependency-analyzer audit. Smallest scope.

What I'd resist until later: anything write-side. Playwright + persistent
profile + per-base `secretSocketId` + a throwaway test base is enough
complexity for one phase. Description sync is the natural first-write
feature when we get there, _not_ push.

## Open questions to resolve before committing

- Does the existing CI/PAT codegen path stay 100% unchanged, or do we want
  the internal API to eventually replace it for some features? (Answer
  shapes whether `LiveBase` is sibling or successor.)
- Is the "code-as-source-of-truth" DSL a worthwhile product direction, or
  is myAirtable's identity strictly codegen+docs? (Determines whether
  `push` is on the roadmap at all, or whether the formula refactoring CLI
  is the natural ceiling.)
- How do we want to handle write-side testing? Throwaway base under a test
  account, run from a developer machine, gated behind an env var? CI
  cannot do this.
