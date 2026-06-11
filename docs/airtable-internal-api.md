# Airtable Internal API — Reference & myAirtable Integration Plan

This document covers two things:

1. **A thorough reference for Airtable's private `v0.3` API** — the same one
   the web UI calls. Reverse-engineered from the
   [`airtable-user-mcp`](https://www.npmjs.com/package/airtable-user-mcp)
   project (`packages/mcp-server/src/{auth,client}.js` in
   `Automations-Project/VSCode-Airtable-Formula`). Endpoint and payload shapes
   below are annotated in that source with capture dates 2026-03-20 →
   2026-04-30 against real session traffic.
2. **A use-case analysis for myAirtable** — where this internal API would
   meaningfully extend what we already do, with implementation sketches for
   the highest-value pieces (Python auth port, schema-diff command, formula
   refactoring CLI).

> Not an official Airtable API. There is no published contract; Airtable can
> change or remove endpoints at any time. Useful for tooling, automation, and
> filling gaps the public REST API leaves open (formulas, rollups, lookups,
> view config, extensions, etc.).

---

# Spike findings — verified against live traffic 2026-06-10

We ran the POC spike (myairtable-oao6) against our own base. Everything below
was observed directly; where it contradicts Part 1, **the spike wins**.

## Q1 — Headless scripted login: WORKS, but only via Firefox

- **PerimeterX protects the login page** (`_px*` cookies) and it specifically
  detects Chromium automation. Vanilla Playwright Chromium, Patchright
  Chromium, and Patchright + real Chrome (`channel="chrome"`) all got the
  "Verify it's you" interstitial — **even headful**. The challenge never
  self-resolves (its widget iframes stay `about:blank` under automation).
- **Playwright Firefox (headless) gets the real login form** and completes
  login. The detector appears to be Chromium-automation-specific.
- Login-form quirks (all required):
  - `fill()` does not enable the React submit button — use
    `press_sequentially()` (real keystrokes).
  - A **Transcend cookie-consent overlay** (`#transcend-shadow-root`)
    intercepts pointer events on both form steps. Block it at the network
    level (`ctx.route` on `*transcend*` → abort) and/or remove the element.
  - The password-step submit button can stay disabled; **press Enter** in the
    password field instead.
  - Two-step form: email → Continue → password appears.
- Login lands on `https://airtable.com/` and the session is immediately valid.

## Q2 — httpx with extracted cookies: WORKS

- Plain httpx with the Firefox session cookies + the §1.5 `x-` headers + a
  matching Firefox User-Agent is **not blocked** by PerimeterX for `/v0.3/`
  reads. No TLS impersonation needed. Transport choice **B confirmed**.
- Use `Accept: application/json`. When a request includes heavy row data
  (e.g. `application/read` with `includeDataForTableIds: ["tbl..."]`), the
  server may respond with a **binary (msgpack-like) streaming format**
  instead of JSON. Schema-only param shapes reliably return JSON. Avoid
  requesting row data at all.

## Q3 — Endpoint shapes: several divergences from Part 1

- **`GET /v0.3/view/{viwId}/readData` exists** (not in Part 1) and is the
  best endpoint for view definitions: returns the viewData object
  **directly** under `data` (not wrapped in `viewDatas[]`), with
  `stringifiedObjectParams={}`. No cell data — the only heavy key is
  `rowOrder` (row IDs in view order; ~500 KB for a 5k-row table), which we
  drop. **Use this for `get_view`.**
- `application/{appId}/read` **requires** the two `may*` flags; omitting
  them → `500 SERVER_ERROR` ("Worker responded with {errorCode}..."). Worked:
  `{"includeDataForTableIds": [], "includeDataForViewIds": null,
"shouldIncludeSchemaChecksum": false,
"mayOnlyIncludeRowAndCellDataForIncludedViews": true,
"mayExcludeCellDataForLargeViews": true}`.
- The live web client sends `secretSocketId` (prefix `soc`) on read GETs,
  but it is **not required** — reads succeed without it.
- `getUserProperties` returns a flat feature-flag map
  (`{"gemini":true,...}`), not `{ data: { userId } }`. Status-code probing
  still works (200 vs 401/403).
- viewData shape divergences:
  - `lastSortsApplied` is `{ sortSet: [...], shouldAutoSort, appliedTime }` —
    an object, **not** a bare array.
  - Extra keys present: `rowOrder`, `sharesById`, `signedUserContentUrls`,
    `applicationTransactionNumber`.
  - `rowHeight` / `metadata` were absent on the views we sampled (likely
    only present when non-default). Model them as optional.
- `tableSchemas[i]` extra keys vs Part 1: `viewsById`, `columnSetById`,
  `meaningfulColumnOrder`, `primaryColumnId`, `rowTemplatesById`, `rowUnit`,
  `isHiddenFromSwitcher`, `dateDependencySettings`. `viewSectionsById` is
  `{}` on a base with no sidebar sections.

## Q4 — Session longevity: ~1 year

- `__Host-airtable-session` expires **a year out** from login. Auto-login
  will be rare.
- Responses set rotating cookies (`AWSALBTG*`, `brw`, `mbpg`) — implement
  cookie write-back to keep the jar fresh, but the session itself is
  long-lived.

## Implementation consequences

- Login engine: **Playwright Firefox, headless** (`playwright install firefox`).
  Patchright/Chromium not needed; msgpack not needed.
- The spike's live session profile persists at `~/.myairtable/spike-profile-ff`
  with storage state at `~/.myairtable/spike-state.json`.

## Investigation 2026-06-10 — batch view fetching (myairtable-vqkq)

For the view-analysis tools we needed all viewDatas of a table/base. Verified
against the live base:

- **`includeDataForViewIds` accepts exactly ONE view.** Two or more (even
  same-type, same-table, correct pairs) → `422 FAILED_STATE_CHECK`. There is
  no batch fetch.
- **`table/{tblId}/readData` with a view included pulls FULL row/cell data**
  for that view's rows (13.6 MB for one 9.7k-row calendar view) — never use
  it for view definitions. `view/{viwId}/readData` (no cell data, only
  `rowOrder`) is the right path, ~0.01–0.51 MB per view depending on type and
  row count.
- **Unknown `stringifiedObjectParams` keys are silently ignored** (tried
  several invented rowOrder-excluding params — no 422, no effect). There is
  no known way to drop `rowOrder` server-side; drop it at parse time and keep
  its length as `row_count`.
- **All six view types** (grid, form, kanban, calendar, gallery, levels)
  return the same viewData shape via `view/readData`; form views lack
  `filters`/`lastSortsApplied` (model them optional). `metadata` appears on
  some types (calendar, levels, form).
- **Other users' personal views ARE readable** via `view/readData` (our base
  has 381 of them) — personal views need no special-casing in coverage
  claims.
- **No row-count field exists anywhere** (checked `table/readData`,
  `getApplicationScaffoldingData` — the latter is tiny: tableById +
  visibleTableOrder only, no view state). Total table row count: use
  `max(len(rowOrder))` across the table's views — exact when an unfiltered
  view exists, a lower bound otherwise.
- `table/readData` with `includeDataForViewIds: []` still returns one
  viewData (the session's `lastViewIdUsed`) and one row in `loadedSlices` —
  don't rely on it returning nothing.

**Chosen fetch strategy:** per-view `GET /v0.3/view/{viwId}/readData`,
bounded concurrency (threads over the shared httpx client), per-view TTL
cache; whole-base scans documented as expensive (~1 call/view).

## Investigation 2026-06-10 — automation read endpoints (myairtable-eang)

Automations live at the UI path `/{appId}/automations` (NOT `/workflows` —
that 404s). "Automations" are "workflows" in the API. Discovered by driving
the Firefox session to the Automations tab and capturing XHR. Endpoints (all
GET, `stringifiedObjectParams={}`, like view reads — `secretSocketId` sent by
the UI but NOT required):

| Endpoint                                                       | Returns                                                                                                                                                              |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `application/{appId}/listWorkflows`                            | `data.workflows[]` — every workflow's id, name, description, deploymentStatus, trigger (type only), graph skeleton (action type ids + wiring). **Configs stripped.** |
| `workflow/{wflId}/read`                                        | `data.workflow` — FULL config: trigger + each action's `inputExpressions` (table ids, filter objects, Gmail bodies, custom scripts, ...).                            |
| `workflowDeployment/{wfdId}/read`                              | deployment detail (not needed for inventory)                                                                                                                         |
| `application/{appId}/readForWorkflows`                         | a workflow-oriented schema variant                                                                                                                                   |
| `application/{appId}/getWorkflowExecutionCountsInCurrentMonth` | run counts                                                                                                                                                           |

**Verified live (45 workflows in our base):**

- `listWorkflows` returns all 45 in one call; **full config requires per-workflow
  `workflow/{id}/read`** (configs are stripped from the list). All 45 read OK,
  including 19 custom-script actions — **full dump is feasible.**
- **Field/table references are extractable**: 45/45 reference table ids,
  36/45 reference field ids, as plain `tbl…`/`fld…` literals inside
  `inputExpressions`. Regex-parseable — this is the future `find_unused_fields`
  / `find_views_using_field` automation signal.
- `deploymentStatus`: 30 deployed, 15 undeployed (proxy for on/off).
- Trigger/action **type ids** are mostly human-readable constants
  (`wttRECORDMATCHES0`, `wttRECORDCREATED0`, `wttRECORDUPDATED0`,
  `wttCRON0000000000`; `watUPDATERECORD00`, `watCREATERECORD00`,
  `watGMAILSENDMAIL0`, `watFINDRECORDS000`, `watCUSTOMSCRIPT00`) — but some are
  opaque hashes (`wttBRZzRXx3C2jyIc` ×29, `watBETUHIcuho4hit` ×13, likely
  integration/first-party-app types) and one action had `null` type. Decode the
  known constants to friendly names; pass unknown ids through verbatim; parse
  defensively (null type ids exist).
- Workflow→section grouping comes from `workflowSectionsById` (already in
  `application/read`; each section has `name` + `workflowOrder`).

**Strategy for list_automations:** `listWorkflows` for the inventory +
section grouping; concurrent per-workflow `workflow/{id}/read` for full
config (same bounded-concurrency + TTL-cache pattern as views); decode known
type ids, pass through unknown; extract referenced table/field ids.

## Investigation 2026-06-10 — computed-field type resolution (myairtable-xby8)

For codegen type disambiguation: does the internal `application/read` schema
resolve computed-field result types better than the public meta API? **Yes —
decisively. GO on schema-first.**

- **Every computed container carries `typeOptions.resultType`.** Verified live:
  formula 609/617, rollup 234/238, count 11/11, lookup all. Overall **1169/1187
  (98%)** of computed fields have a resolved `resultType`; of the **389**
  fields the public API leaves ambiguous (our `result_type()` returns
  `singleLineText`/empty), the internal schema resolves **389/389 (100%)**.
- **Lookups are internally typed `"lookup"`, NOT `multipleLookupValues`** (the
  public-API name). They carry `resultType` + `resultIsArray` +
  `foreignTableRollupColumnType` (the source field's type) + format keys. Any
  resolver must read internal type `"lookup"`, not the public type name.
- **`resultType` vocabulary is a small base set**: `text`, `number`, `date`,
  `checkbox`. Plus **`resultIsArray`** (so `text[]`, `number[]`, `date[]` —
  e.g. multi-value lookups/rollups). This is the correct _base_ type for
  language mapping (currency/percent/count all → `number` → float, which is
  right for Python/TS/Rust types).
- **Finer semantics ARE recoverable from `typeOptions`**, so coarse
  `resultType` is not a regression:
  - date vs dateTime: `isDateTime` (bool), `dateFormat`, `timeFormat`,
    `timeZone`. (A few date fields lack these keys → default to date.)
  - currency/percent: `format` (`"currency"`), `precision`, `symbol` on
    rollups/lookups/formulas.
    So the resolver can produce `resultType` + `resultIsArray` + the refinements,
    matching or beating our current inference without losing currency/dateTime.
- **`getUnsavedColumnConfigResultType` (the validator fallback) is a POST** and
  404s on GET — it needs the deferred mutation transport (CSRF +
  secretSocketId, §1.6). Not available now. **But schema coverage is high
  enough (98% / 100% of ambiguous) that v1 does not need it** — defer the
  validator fallback until/if write support exists.

**Verdict:** mechanism (1), reading `typeOptions.{resultType, resultIsArray,
isDateTime, format, ...}` from the internal `application/read` schema (which
the internal tooling already fetches), fully covers the disambiguation need.
The resolver normalizes these to the codegen type vocabulary; the persisted
type-map captures them so CI codegen stays PAT-only. Validator fallback is
deferred (and gated on the write transport).

---

# Part 1 — Internal API Reference

## 1. Auth & session model

There is no API key. The internal API authenticates via your normal logged-in
**browser session cookie**, plus a CSRF token, plus (for some mutations) a
per-base `secretSocketId`. The reference implementation drives a real
Chromium profile (Patchright) and calls `fetch()` from inside the page
context, so cookies attach automatically.

### 1.1 Cookie / session

- Login goes through the live Airtable login flow in a Chromium context.
- The browser profile is persisted to disk so sessions survive across
  processes.
- Session validity is probed by `GET /v0.3/getUserProperties`. A 401/403 or a
  redirect to `/login` triggers re-init.

### 1.2 CSRF token

Extracted from the loaded `airtable.com` page in this priority order:

1. Any `<script>` whose text contains `"csrfToken":"..."` (JSON blob).
2. `#__NEXT_DATA__` → `props.pageProps.csrfToken`.
3. `<meta name="csrf-token">`.
4. Any `window.<key>.csrfToken` global.

For form-encoded POSTs the token is appended as a `_csrf=<token>` URL-encoded
field. JSON POSTs do **not** include `_csrf`; the JSON path is used for a
narrower set of internal endpoints — the form path is the dominant one.

### 1.3 secretSocketId

Required by many mutating endpoints. It is **per-base** and rotates per
session. The reference implementation captures it passively by listening on
Chromium's `request` event for any POST whose body matches
`secretSocketId[=:]([^&"]+)` and whose URL contains an `appXXX...` ID, then
caches `{ appId → socketId }` in an LRU map.

If a mutation is sent without a captured `secretSocketId`, the request is
sent anyway and the server may reject it. The client must refuse to share a
socketId across bases — using base A's socketId on base B is a correctness
hazard, not just a permission failure.

### 1.4 Other request-scoped IDs

| ID              | Format            | Source                                                               |
| --------------- | ----------------- | -------------------------------------------------------------------- |
| `requestId`     | `req` + 14 base62 | client-generated per request                                         |
| `pageLoadId`    | `pgl` + 13 base36 | client-generated per request                                         |
| `filter.id`     | `flt` + 14 base62 | client-generated, **required on every leaf and nested filter group** |
| `sort.id`       | `srt` + 14 base62 | client-generated when omitted by caller                              |
| `groupLevel.id` | `glv` + 14 base62 | client-generated when omitted                                        |

For _create_ endpoints the client picks the new object's ID itself (e.g. you
POST to `/column/{newFldId}/create`). New IDs are 3-letter prefix + 14 base62
characters using a CSPRNG (`crypto.randomBytes(14)`).

### 1.5 Required headers

All requests:

```
x-airtable-inter-service-client: webClient
x-airtable-page-load-id:        pgl<13 base36>
x-requested-with:               XMLHttpRequest
x-user-locale:                  en
x-time-zone:                    <IANA tz, e.g. America/New_York>
x-airtable-application-id:      <appId, when scoped to a base>
```

Form mutations also send:

```
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept:       application/json, text/javascript, */*; q=0.01
```

JSON endpoints use `Content-Type: application/json`.

### 1.6 Standard mutation envelope

Every form mutation sends a body shaped like:

```
stringifiedObjectParams=<JSON-stringified payload>
requestId=req<14 chars>
secretSocketId=<captured per-app, when known>
_csrf=<csrf token>
```

The "real" payload lives entirely inside `stringifiedObjectParams` — there is
no top-level body field for it. URL path arguments (`appId`, `tableId`,
`viewId`, etc.) are _not_ repeated in the payload unless the endpoint
explicitly needs the parent (e.g. `tableId` when creating a column).

### 1.7 Recommended client-side robustness

The reference client implements these and you should too if porting:

- Single in-process **request queue** — Playwright's `page.evaluate` is not
  safe under concurrent calls.
- **Bounded queue** — reject when saturated rather than accept unbounded
  backlog from a runaway agent loop.
- **15s per-evaluate timeout** — Playwright has no built-in timeout on
  `page.evaluate`; a CDP-dead Chromium can hang forever.
- **30s wall-clock budget** for any single API call (across retries).
- **Session recovery** on 401/403/network-error: close context, relaunch,
  re-verify, retry once.
- **Exponential backoff** on 429/503: 500 ms × 2ⁿ, max 3 retries.
- **secretSocketId cache** — per-appId, never shared across bases, LRU-capped.

---

## 2. Read endpoints

| Method | Path                                                                       | Purpose                                                                                                 |
| ------ | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `GET`  | `/v0.3/getUserProperties`                                                  | Logged-in user info; session-validity probe. Returns `{ data: { userId, ... } }`.                       |
| `GET`  | `/v0.3/application/{appId}/read?stringifiedObjectParams=...&requestId=...` | Full base schema: `{ data: { tableSchemas: [...], ... } }`. Cache for ~30s.                             |
| `GET`  | `/v0.3/{appId}/getApplicationScaffoldingData`                              | Lighter scaffolding payload (note: appId is at the URL root, NOT under `/application/`).                |
| `GET`  | `/v0.3/table/{tableId}/readData?stringifiedObjectParams=...&requestId=...` | Live view state (filters, sorts, group levels, columnOrder, frozenColumnCount, colorConfig, rowHeight). |

`stringifiedObjectParams` for `application/read`:

```json
{
	"includeDataForTableIds": null,
	"includeDataForViewIds": null,
	"shouldIncludeSchemaChecksum": false
}
```

`stringifiedObjectParams` for `table/{tableId}/readData`:

```json
{
	"includeDataForViewIds": ["viwXXX"],
	"shouldIncludeSchemaChecksum": false,
	"mayOnlyIncludeRowAndCellDataForIncludedViews": true,
	"mayExcludeCellDataForLargeViews": true
}
```

### Schema response shape (key paths)

- `data.tableSchemas[i]` → `{ id, name, columns | fields, views, viewOrder, viewSectionsById }`
- `data.tableSchemas[i].columns[j]` → `{ id, name, type, typeOptions, description }`
- `data.tableSchemas[i].views[j]` → `{ id, name, type, createdByUserId, personalForUserId }` (static metadata only — see §2 below for dynamic state)
- `data.tableSchemas[i].viewSectionsById` → `{ [vscId]: { id, name, viewOrder, pinnedForUserId, createdByUserId } }`
- `data.tableSchemas[i].viewOrder` interleaves `viw...` and `vsc...` IDs in
  display order — this is the source of truth for sidebar ordering.

> The realtime WebSocket delta model uses a different key for sections:
> `tables.{tblId}.viewSections`. Don't confuse them. The HTTP read response
> uses `viewSectionsById`.

### View state from `readData`

```
data.viewDatas[i] = {
  id, type,
  filters:           { filterSet, conjunction },
  lastSortsApplied:  [ { id, columnId, ascending } ],
  groupLevels:       [ { id, columnId, order, emptyGroupState } ],
  columnOrder:       [ { columnId, visibility, width? } ],
  frozenColumnCount,
  colorConfig,
  rowHeight,
  metadata:          { grid: { rowHeight }, ... },
  description,
  createdByUserId,
}
```

The `application/read` endpoint **does not** include any of this dynamic
state. To know what a view actually does (filters, sorts, grouping,
visibility), you must hit `readData`.

---

## 3. Mutation endpoints

All POSTs unless noted. URL path = `https://airtable.com/v0.3/<path>`.
Payload is the object that goes inside `stringifiedObjectParams`.

### 3.1 Tables

| Path                                             | Payload                                                                        | Notes                                                                                                |
| ------------------------------------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `table/{newTblId}/create`                        | `{ applicationId, name }`                                                      | Caller mints the new `tblXXX` ID.                                                                    |
| `table/{tblId}/updateName`                       | `{ name }`                                                                     | Rename.                                                                                              |
| `table/{tblId}/destroy`                          | `{}`                                                                           | Delete. Cannot delete the only table in a base.                                                      |
| `table/{tblId}/getUnsavedColumnConfigResultType` | `{ config: { default: null, type: "formula", typeOptions: { formulaText } } }` | Validate a formula before saving. Returns `{ data: { pass, resultType } }`.                          |
| `table/{tblId}/moveViewOrViewSection`            | `{ viewIdOrViewSectionId, targetIndex, targetViewSectionId? }`                 | Single endpoint for: move view into section, move view out, reorder section, reorder within section. |

### 3.2 Columns (fields)

Fields are called _columns_ in the URL but _fields_ in most response shapes.

| Path                               | Payload                                                                                     |
| ---------------------------------- | ------------------------------------------------------------------------------------------- |
| `column/{newFldId}/create`         | `{ tableId, name, config: { type, typeOptions }, description?, afterOverallColumnIndex? }`  |
| `column/{fldId}/updateConfig`      | `{ type, typeOptions, schemaDependenciesCheckParams? }` ← **flat, NOT wrapped in `config`** |
| `column/{fldId}/updateName`        | `{ name }`                                                                                  |
| `column/{fldId}/updateDescription` | `{ description }`                                                                           |
| `column/{fldId}/destroy`           | Step 1: `{ checkSchemaDependencies: true }`. Step 2 (force): `{}`.                          |
| `column/{newFldId}/createAsClone`  | `{ tableId, activeViewId, columnIdToClone, shouldDuplicateCells, afterOverallColumnIndex }` |

#### Field-type aliases (UI ⇄ internal)

The internal API does not expose `url`, `email`, `phone`, `dateTime` as
top-level types. They're variations on `text` / `date`:

| Public name | Internal `type` | `typeOptions`                                                                   |
| ----------- | --------------- | ------------------------------------------------------------------------------- |
| URL         | `text`          | `{ validatorName: "url" }`                                                      |
| Email       | `text`          | `{ validatorName: "email" }`                                                    |
| Phone       | `text`          | `{ validatorName: "phoneNumber" }`                                              |
| DateTime    | `date`          | `{ isDateTime: true, dateFormat, timeFormat, timeZone, shouldDisplayTimeZone }` |

`dateFormat` / `timeFormat` are **flat strings** (`"Local"`, `"iso"`,
`"friendly"`, `"24hour"`, `"12hour"`) — _not_ `{ name: "iso" }` as in the
public REST API. Defaults the reference client uses when omitted:
`dateFormat: "Local"`, `timeFormat: "24hour"`, `timeZone: "UTC"`,
`shouldDisplayTimeZone: true`.

#### Two-step delete

`column/{fldId}/destroy` with `{ checkSchemaDependencies: true }` returns
either:

- `200` — field deleted, no dependents.
- `422 SCHEMA_DEPENDENCIES_VALIDATION_FAILED` — body contains
  `error.details.applicationDependencyGraphEdgesBySourceObjectId[fldId]`
  describing every dependent (other fields, view filters/sorts/groupings).

To force, repost the same URL with `{}`.

### 3.3 Views

| Path                                          | Payload                                                                                                               |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `view/{newViwId}/create`                      | `{ tableId, name, type, copyFromViewId, copyMode: "new"\|"duplicate", personalForUserId, lock }`                      |
| `view/{viwId}/updateName`                     | `{ name, origin: "viewName" }`                                                                                        |
| `view/{viwId}/destroy`                        | `{}`                                                                                                                  |
| `view/{viwId}/updateDescription`              | `{ description }`                                                                                                     |
| `view/{viwId}/updateFilters`                  | `{ filters: { filterSet, conjunction: "and"\|"or" } \| null }`                                                        |
| `view/{viwId}/updateMultipleViewConfigs`      | `{ targetOverallColumnIndicesById: { fldId: index, ... } }` ← used to reorder all fields by overall index             |
| `view/{viwId}/showOrHideAllColumns`           | `{ visibility: bool }`                                                                                                |
| `view/{viwId}/showOrHideColumns`              | `{ columnIds: [fldId, ...], visibility: bool }`                                                                       |
| `view/{viwId}/applySorts`                     | `{ sortObjs: [{ id: srt..., columnId, ascending }], shouldAutoSort: true }`                                           |
| `view/{viwId}/updateGroupLevels`              | `{ groupLevels: [{ id: glv..., columnId, order: "ascending"\|"descending", emptyGroupState: "hidden"\|"visible" }] }` |
| `view/{viwId}/updateRowHeight`                | `{ rowHeight: "small"\|"medium"\|"large"\|"xlarge" }`                                                                 |
| `view/{viwId}/moveVisibleColumns`             | `{ columnIds, targetVisibleIndex }` ← visible-only index space                                                        |
| `view/{viwId}/moveOverallColumns`             | `{ columnIds, targetOverallIndex }` ← visible + hidden index space                                                    |
| `view/{viwId}/updateFrozenColumnCount`        | `{ frozenColumnCount: number }`                                                                                       |
| `view/{viwId}/updateCoverColumnId`            | `{ coverColumnId: fldId \| null }` (Kanban / Gallery)                                                                 |
| `view/{viwId}/updateCoverFitType`             | `{ coverFitType: "fit"\|"crop" }`                                                                                     |
| `view/{viwId}/updateColorConfig`              | `{ colorConfig: { type: "selectColumn", ... } }`                                                                      |
| `view/{viwId}/updateShouldWrapCellValues`     | `{ shouldWrapCellValues: bool }`                                                                                      |
| `view/{viwId}/updateCalendarDateColumnRanges` | `{ dateColumnRanges: [{ startColumnId, endColumnId? }] }`                                                             |

Supported view `type` values: `"grid"`, `"form"`, `"kanban"`, `"calendar"`,
`"gallery"`, `"gantt"`, `"levels"` (sidebar shows it as "list").

#### View create requires `copyFromViewId`

The internal API mandates a source view to copy initial config from. Pass any
existing view ID. With `copyMode: "new"` the new view starts blank-ish (but
still inherits visibility — see §4.4). With `copyMode: "duplicate"` it's an
exact clone.

#### Filter object shape

A leaf filter:

```json
{
	"id": "flt<14>",
	"columnId": "fldXXX",
	"operator": "=",
	"value": "..."
}
```

A nested group (max nesting depth = 2 — top conjunction + one nested layer):

```json
{
  "id": "flt<14>",
  "type": "nested",
  "conjunction": "and" | "or",
  "filterSet": [ ...leaves or further nesting... ]
}
```

Operators that appear in real traffic: `=`, `!=`, `>`, `>=`, `<`, `<=`,
`contains`, `doesNotContain`, `isAnyOf`, `isNoneOf`, `isEmpty`, `isNotEmpty`,
`filename`, `filetype`. The UI uses `=` / `!=` for text/single-select even
though some docs mention `is` / `isNot` / `isAnyOf`.

### 3.4 View Sections (sidebar grouping)

| Path                             | Payload                                                                            |
| -------------------------------- | ---------------------------------------------------------------------------------- |
| `viewSection/{newVscId}/create`  | `{ tableId, name }`                                                                |
| `viewSection/{vscId}/updateName` | `{ name }`                                                                         |
| `viewSection/{vscId}/destroy`    | `{}` (contained views auto-promoted to ungrouped at the section's former position) |

Movement (in/out of a section, or reordering sections) goes through
`table/{tblId}/moveViewOrViewSection` — see §3.1.

### 3.5 Form view metadata (legacy form views)

Each property has its own atomic endpoint:

| Path                                                              | Payload                                                             |
| ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| `view/{viwId}/updateFormDescription`                              | `{ description }`                                                   |
| `view/{viwId}/updateFormAfterSubmitMessage`                       | `{ afterSubmitMessage }`                                            |
| `view/{viwId}/updateFormRedirectUrl`                              | `{ redirectUrl }`                                                   |
| `view/{viwId}/updateFormRefreshAfterSubmit`                       | `{ refreshAfterSubmit }`                                            |
| `view/{viwId}/updateFormShouldAllowRequestCopyOfResponse`         | `{ shouldAllowRequestCopyOfResponse: bool }`                        |
| `view/{viwId}/updateFormShouldAttributeResponses`                 | `{ shouldAttributeResponses: bool }`                                |
| `view/{viwId}/updateFormIsAirtableBrandingRemoved`                | `{ isAirtableBrandingRemoved: bool }`                               |
| `view/{viwId}/updateFormSubmissionNotificationPreferencesForUser` | `{ userId: "usr...", shouldEnable: bool }` (per-user, not per-form) |

Newer "Interfaces" / builder forms use a separate `page/*` endpoint family
that the reference client intentionally does not cover.

### 3.6 Extensions / Blocks

Internal model:

- A **block** (`blkXXX`) is the registration of an extension within a base.
- A **block installation page** (`bipXXX`) is a dashboard tab.
- A **block installation** (`bliXXX`) is an instance of a block placed on a
  page.

| Path                                         | Payload                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------- |
| `block/{newBlkId}/create`                    | `{ name, applicationId, latestReleaseId }`                                 |
| `blockInstallationPage/{newBipId}/create`    | `{ applicationId, name, developmentBlockId: null, developerUserId: null }` |
| `blockInstallation/{newBliId}/create`        | `{ blockInstallationPageId, blockId, name, type: "release" }`              |
| `blockInstallation/{bliId}/updateState`      | `{ state }` (enable/disable)                                               |
| `blockInstallation/{bliId}/updateName`       | `{ name }`                                                                 |
| `blockInstallation/{newBliId}/createAsClone` | `{ blockInstallationIdToClone, blockInstallationPageId }`                  |
| `blockInstallation/{bliId}/destroy`          | `{}`                                                                       |

---

## 4. Quirks, gotchas & undocumented constraints

These are sharp edges the reference client works around explicitly. If you
call the API directly you must reproduce these.

### 4.1 Naming asymmetries

- Delete endpoints are `/destroy`, not `/delete`.
- Rename endpoints are `/updateName`, not `/rename`.
- Field is _column_ in the URL but _field_ in most response shapes.
- Field create wraps in `config: { type, typeOptions }`. Field
  `updateConfig` is **flat** — no `config` wrapper. This trips up
  re-implementers most often.

### 4.2 Filter normalization

The API rejects several documented combinations with opaque
`422 FAILED_STATE_CHECK`. Known cases:

- `is` / `isNot` on text or single-select → must be sent as `=` / `!=`.
- `isAnyOf` with a single value → must collapse to `=` with a scalar value.
- `isEmpty` / `isNotEmpty` on field types `text`, `formula(text)`, `lookup`,
  `rollup` → must be rewritten to `=` / `!=` against the empty string `""`.
- `isEmpty` / `isNotEmpty` on `foreignKey` (linked-record) fields →
  **no client-side workaround**. Create a transitive helper formula
  (e.g. `IF(LEN({Linked} & "")>0,"yes","")`) and filter on that.
- Nested filter groups deeper than 2 levels → rejected. Flatten by repeating
  shared conditions inside each leaf group.
- Every filter object — leaf and nested — must carry a unique `id` field
  prefixed `flt`. The endpoint silently 422s if any is missing.

### 4.3 Field-type encoding

- URL/Email/Phone are `type: "text"` with `typeOptions.validatorName`.
- DateTime is `type: "date"` with `typeOptions.isDateTime: true`.
- `dateFormat` / `timeFormat` are flat strings, not `{ name: "..." }`.

### 4.4 Column reorder pitfalls

- `updateMultipleViewConfigs` requires a **complete** `targetOverallColumnIndicesById`
  map covering every field in the view. Passing a partial map 422s. The
  reference client merges the partial map with the current order.
- `moveVisibleColumns` cannot place anything at visible-index 0 in a grid
  view — that slot is reserved for the pinned primary column. Insert at
  index ≥ 1.
- Per-column moves of an already-correctly-positioned column also 422.
  Use a single batched call instead of looping.
- Newly created views (even with `copyMode: "new"`) inherit _all_ current
  fields as visible. There is no "blank view" mode; you must explicitly
  hide-all then show-the-curated-set.

### 4.5 Schema response keys

- `application/{appId}/read` surfaces sidebar sections under
  `table.viewSectionsById` (rich shape). The realtime WebSocket delta model
  uses `tables.{tblId}.viewSections`. Don't confuse them.
- `table.viewOrder` includes both `viw...` and `vsc...` IDs inline in display
  order.

### 4.6 Safety patterns the reference client enforces

- `delete_field` / `delete_table` require an `expectedName` matching the
  current name — guards against deleting the wrong object after a rename.
- All Airtable IDs validated against `/^[a-z]{3}[A-Za-z0-9]+$/` before
  building URLs, to prevent path traversal.
- Mutating endpoints serialized through a single in-process queue.
- 401/403/network-error → one session-recovery + retry.
- 429/503 → exponential backoff (500 ms × 2ⁿ), max 3 retries.
- `secretSocketId` cached **per appId**, never shared across bases.

---

## 5. Error-response shapes seen in the wild

```jsonc
// Generic mutation rejection
{ "error": { "type": "FAILED_STATE_CHECK" } }

// Field-delete dependency check
{
  "error": {
    "type": "SCHEMA_DEPENDENCIES_VALIDATION_FAILED",
    "details": {
      "applicationDependencyGraphEdgesBySourceObjectId": {
        "fldXXX": [
          { "targetObjectId": "viwYYY", "dependencyType": "viewFilter" },
          { "targetObjectId": "fldZZZ", "dependencyType": "formulaReference" }
        ]
      }
    }
  }
}
```

`dependencyType` strings observed: `viewFilter`, `viewSort`, `viewGroup`,
`formulaReference`, `lookupReference`, `rollupReference`. Targets prefixed
`viw` are view-bound dependencies; `fld` are downstream field references.

---

## 6. Quick capability ⇄ endpoint map

| Capability                                   | Endpoint(s)                                                                                                                                                         |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Read full base schema                        | `GET /application/{appId}/read`                                                                                                                                     |
| Read live view state                         | `GET /table/{tableId}/readData`                                                                                                                                     |
| Validate formula before saving               | `POST /table/{tableId}/getUnsavedColumnConfigResultType`                                                                                                            |
| Create / rename / delete table               | `POST /table/{tableId}/{create,updateName,destroy}`                                                                                                                 |
| Field CRUD + clone + descriptions            | `POST /column/{fldId}/{create,updateConfig,updateName,updateDescription,destroy,createAsClone}`                                                                     |
| Create / rename / delete / duplicate view    | `POST /view/{viwId}/{create,updateName,destroy}` (+ `copyMode: "duplicate"`)                                                                                        |
| View filters / sorts / groups / rowHeight    | `POST /view/{viwId}/{updateFilters,applySorts,updateGroupLevels,updateRowHeight}`                                                                                   |
| Column visibility / order / freeze in a view | `POST /view/{viwId}/{showOrHideAllColumns,showOrHideColumns,moveVisibleColumns,moveOverallColumns,updateMultipleViewConfigs,updateFrozenColumnCount}`               |
| Kanban/Gallery cover & color                 | `POST /view/{viwId}/{updateCoverColumnId,updateCoverFitType,updateColorConfig}`                                                                                     |
| Calendar date ranges                         | `POST /view/{viwId}/updateCalendarDateColumnRanges`                                                                                                                 |
| Form view metadata                           | `POST /view/{viwId}/updateForm*`                                                                                                                                    |
| Sidebar sections                             | `POST /viewSection/{vscId}/{create,updateName,destroy}` + `POST /table/{tblId}/moveViewOrViewSection`                                                               |
| Extensions (blocks)                          | `POST /block/{blkId}/create`, `POST /blockInstallation/{bliId}/{create,createAsClone,updateName,updateState,destroy}`, `POST /blockInstallationPage/{bipId}/create` |

---

## 7. ID prefix reference

| Entity             | Prefix | Example                                    |
| ------------------ | ------ | ------------------------------------------ |
| Base / app         | `app`  | `appXXXXXXXXXXXXXX`                        |
| Table              | `tbl`  | `tblXXXXXXXXXXXXXX`                        |
| Field (column)     | `fld`  | `fldXXXXXXXXXXXXXX`                        |
| View               | `viw`  | `viwXXXXXXXXXXXXXX`                        |
| View section       | `vsc`  | `vscXXXXXXXXXXXXXX`                        |
| Filter object      | `flt`  | `fltXXXXXXXXXXXXXX`                        |
| Sort object        | `srt`  | `srtXXXXXXXXXXXXXX`                        |
| Group level        | `glv`  | `glvXXXXXXXXXXXXXX`                        |
| Block (extension)  | `blk`  | `blkXXXXXXXXXXXXXX`                        |
| Block installation | `bli`  | `bliXXXXXXXXXXXXXX`                        |
| Dashboard page     | `bip`  | `bipXXXXXXXXXXXXXX`                        |
| User               | `usr`  | `usrXXXXXXXXXXXXXX`                        |
| Request ID         | `req`  | `reqXXXXXXXXXXXXXX`                        |
| Page-load ID       | `pgl`  | `pglXXXXXXXXXXXXX` (13 chars after prefix) |

---

# Part 2 — myAirtable Integration Plan

myAirtable today is built on the public meta API
(`api.airtable.com/v0/meta/bases/{base_id}/tables`) — read-only, PAT-scoped,
CI-friendly. It generates code (Python/TS/JS/Rust ORMs + formula builders),
docs (Markdown for Obsidian + HTML), and exposes 24 read-only schema
introspection tools via MCP.

The internal API would let myAirtable do things the public API simply does
not expose. This section ranks where it fits.

## 8. Use cases, ranked by value-to-effort

### 8.1 High value, low risk — read-only enrichment

1. **Live view state in docs and codegen.** Today a generated view is just
   `{id, name, type}`. With `table/{tableId}/readData` we get filters, sorts,
   group levels, columnOrder, frozenColumnCount, colorConfig, rowHeight.
   - Markdown/HTML docs render _what each view actually does_:
     _"View `Active Projects`: filters where `{Status}='Active'` AND
     `{Owner}=CURRENT_USER()`, sorted by `{DueDate}` desc."_
   - Codegen emits typed view constants:
     `ContactsModel.views.active_clients.filter_formula`. The user calls
     `airtable.contacts.get(view=ContactsModel.views.active_clients)` with
     the actual filter visible at type-check time.
   - The column order & visibility can drive a sensible default `fields=[...]`
     parameter on `.get()`.

2. **Sidebar sections in docs.** `viewSectionsById` + `viewOrder` group views
   the way they appear in the Airtable sidebar. Currently myAirtable's docs
   render a flat per-table view list.

3. **Authoritative dependency graph.** Today
   `trace_field_dependencies` / `reverse_dependencies` / `find_dead_fields` /
   `find_circular_references` parse formula text in
   `src/formulas/formula_*.py`. The internal API's
   `column/{fldId}/destroy` precheck returns Airtable's own dependency
   graph. We can:
   - Cross-validate our parser against ground truth in tests.
   - Surface link/lookup/rollup edges our text parser misses.
   - Power a more accurate `find_dead_fields` that uses Airtable's reachability.

4. **New MCP tools that pair with existing ones:**
   - `validate_formula` — backs `transpile` with Airtable's own validator.
     If our transpiled output's reported `resultType` differs from our
     static type inference, that's a real lead on a transpiler bug.
   - `get_view` — full state, not just metadata. Pairs with
     `describe_table` and friends.
   - `get_view_sections` — sidebar grouping.
   - `get_field_dependencies` — authoritative graph.

### 8.2 High value, high risk — write-side schema management

5. **`myairtable push` — code as source-of-truth.** The transformative use
   case. We already model tables/fields/types in Python; the missing half
   is _applying_ a diff back to Airtable.
   - `myairtable push --plan` → diff (fields to create, rename, retype,
     delete; tables to create/rename/delete).
   - `myairtable push --apply` → calls `column/{id}/{create,updateConfig,
updateName,destroy}`, `table/{id}/create`, etc.
   - Special-cases formula / rollup / lookup / count fields, which the
     public REST API explicitly cannot create.
   - Closes the loop on the existing CSV name-locking feature: the CSV
     today pins generated _property_ names; with `--rename-airtable`, those
     names can also be pushed _into_ Airtable.

6. **Formula refactoring CLI.** Wires the existing
   transpiler/flattener/formatter/highlighter/sanitizer/condenser to
   `column/{fldId}/updateConfig`:
   - `myairtable formula format --apply` — reformat every formula in the base.
   - `myairtable formula flatten <field>` — inline a helper into its
     consumers, then delete the helper.
   - `myairtable formula rename-field <fldX> <new>` — rename a field and
     rewrite every formula that references it.
   - Pre-flight every change with `validate_formula`.

   Niche but uniquely valuable to power users — nothing else does this.

### 8.3 Medium value — bulk QoL

7. **Bulk select-option / choice rename.** Renaming a single-select choice
   in Airtable is tedious. The generators already know the choices; expose a
   CLI that `updateFieldConfig`s them in bulk.

8. **Description sync.** Markdown docs already include rich field
   descriptions written by users. `column/{id}/updateDescription` lets
   `myairtable docs --push-descriptions` write them back so they're visible
   in the Airtable UI.

### 8.4 Low fit — skip

- **Extension / dashboard management.** Available in the API but not aligned
  with myAirtable's identity as a codegen/docs tool.
- **Form metadata.** Same — niche surface area; outside scope.

## 9. Caveats — read these before committing

- **Auth model is incompatible with current setup.** myAirtable today is
  PAT + httpx, runs cleanly in CI, single-binary install. The internal API
  requires a logged-in Chromium session (Patchright/Playwright), CSRF, and a
  per-base `secretSocketId` scraped off network traffic. That's a ~170 MB
  dependency and a manual login step. Not appropriate for the read-only
  codegen path that runs in CI.
- **Hybrid is the right design.** Keep the public meta API as the default
  backend (CI-safe, deterministic). Add an `internal_api` backend that's
  opt-in for the features that genuinely need it. Mirror the
  `airtable-user-mcp` repo's split between public and internal.
- **Python port effort is non-trivial** but tractable — see §10 below.
- **Stability risk.** The reference doc shows traffic captures dated
  2026-03 → 2026-04 with workarounds for endpoint changes. Airtable can
  break v0.3 anytime. Anything write-side needs feature flags so a single
  endpoint change doesn't take down the whole tool.

## 10. Implementation sketch — Python auth port

The reference auth layer is ~570 lines of JS. Most of it is recoverable in
a similar amount of Python. The mechanical operation is the same:
launch Playwright, navigate to airtable.com, do a `fetch()` from inside the
page so cookies attach automatically.

### 10.1 Dependency footprint

```toml
# pyproject.toml addition (optional extra)
[project.optional-dependencies]
internal = [
  "playwright >= 1.41",   # or "patchright" for stealth
]
```

Install browser engine once: `playwright install chromium`.

### 10.2 File layout

```
src/internal_api/
  __init__.py
  auth.py        # PlaywrightAuth — session, CSRF, secretSocketId, queue, retries
  client.py      # AirtableInternalClient — endpoint methods (mirror client.js)
  ids.py         # generate_id, validate_airtable_id
  filters.py     # normalize_filter_set, ensure_filter_ids, etc.
  errors.py      # InternalApiError, FilterError, DependencyError
```

### 10.3 Auth skeleton (Python)

```python
# src/internal_api/auth.py
import asyncio
import os
import re
import secrets
import string
from collections import OrderedDict
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext

_BASE62 = string.ascii_letters + string.digits


def _gen_id(prefix: str, length: int = 14) -> str:
    body = "".join(secrets.choice(_BASE62) for _ in range(length))
    return f"{prefix}{body}"


def _gen_page_load_id() -> str:
    return _gen_id("pgl", 13)


class AirtableInternalAuth:
    """Logged-in Airtable session via persistent Chromium profile."""

    def __init__(self, profile_dir: Path | None = None, headless: bool = True):
        self.profile_dir = profile_dir or Path.home() / ".myairtable" / "chrome-profile"
        self.headless = headless
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.csrf_token: str | None = None
        self._socket_ids: OrderedDict[str, str] = OrderedDict()
        self._socket_cap = 50
        self._lock = asyncio.Lock()  # serialize page.evaluate

    async def init(self) -> None:
        if self.context:
            return
        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            channel="chrome",
            viewport=None,
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self._wire_socket_id_capture()
        await self.page.goto("https://airtable.com/", wait_until="domcontentloaded", timeout=30_000)
        await self._wait_for_app_ready()
        await self._extract_csrf()
        await self._verify_session()

    def _wire_socket_id_capture(self) -> None:
        pat = re.compile(r"secretSocketId[=:]([^&\"]+)")
        app_pat = re.compile(r"(app[A-Za-z0-9]+)")

        def on_request(req):
            try:
                if req.method != "POST" or "airtable.com" not in req.url:
                    return
                body = req.post_data
                if not body:
                    return
                m = pat.search(body)
                if not m:
                    return
                am = app_pat.search(req.url)
                if not am:
                    return
                app_id = am.group(1)
                # LRU touch
                if app_id in self._socket_ids:
                    del self._socket_ids[app_id]
                self._socket_ids[app_id] = m.group(1)
                while len(self._socket_ids) > self._socket_cap:
                    self._socket_ids.popitem(last=False)
            except Exception:
                pass

        self.page.on("request", on_request)

    async def _extract_csrf(self) -> None:
        self.csrf_token = await self.page.evaluate("""() => {
            for (const s of document.querySelectorAll('script')) {
              const m = (s.textContent || '').match(/"csrfToken"\\s*:\\s*"([^"]+)"/);
              if (m) return m[1];
            }
            const next = document.getElementById('__NEXT_DATA__');
            if (next) {
              try {
                const d = JSON.parse(next.textContent);
                if (d?.props?.pageProps?.csrfToken) return d.props.pageProps.csrfToken;
              } catch {}
            }
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.content : null;
        }""")

    async def _verify_session(self) -> None:
        result = await self._raw_call("GET", "/v0.3/getUserProperties")
        if result["status"] != 200:
            raise RuntimeError(
                "Session invalid. Run: python -m myairtable.internal login"
            )

    async def _wait_for_app_ready(self) -> None:
        try:
            await self.page.wait_for_selector("#__NEXT_DATA__", timeout=10_000)
        except Exception:
            await self.page.wait_for_timeout(3_000)
        url = self.page.url
        if "/login" in url or "/signin" in url:
            raise RuntimeError(
                f"Session expired: redirected to {url}. Run login."
            )

    def get_secret_socket_id(self, app_id: str) -> str | None:
        return self._socket_ids.get(app_id)

    async def _raw_call(
        self,
        method: str,
        url_path: str,
        body: dict[str, Any] | None = None,
        app_id: str | None = None,
    ) -> dict[str, Any]:
        url = url_path if url_path.startswith("http") else f"https://airtable.com{url_path}"
        page_load_id = _gen_page_load_id()
        csrf = self.csrf_token

        async with self._lock:
            return await self.page.evaluate("""
              async ({url, method, body, appId, pageLoadId, csrf}) => {
                const headers = {
                  'x-airtable-inter-service-client': 'webClient',
                  'x-airtable-page-load-id': pageLoadId,
                  'x-requested-with': 'XMLHttpRequest',
                  'x-user-locale': 'en',
                  'x-time-zone': Intl.DateTimeFormat().resolvedOptions().timeZone,
                };
                if (appId) headers['x-airtable-application-id'] = appId;
                let bodyStr;
                if (body && method !== 'GET') {
                  headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
                  headers['Accept'] = 'application/json, text/javascript, */*; q=0.01';
                  const params = new URLSearchParams(body);
                  if (csrf) params.set('_csrf', csrf);
                  bodyStr = params.toString();
                }
                try {
                  const res = await fetch(url, { method, headers, body: bodyStr });
                  return { status: res.status, body: await res.text() };
                } catch (e) { return { status: 0, body: '', error: e.message }; }
              }
            """, {"url": url, "method": method, "body": body, "appId": app_id,
                  "pageLoadId": page_load_id, "csrf": csrf})

    async def get(self, url: str, app_id: str | None = None) -> dict[str, Any]:
        return await self._raw_call("GET", url, None, app_id)

    async def post_form(
        self,
        url: str,
        payload: dict[str, Any],
        app_id: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "stringifiedObjectParams": __import__("json").dumps(payload),
            "requestId": _gen_id("req"),
        }
        sock = app_id and self.get_secret_socket_id(app_id)
        if sock:
            body["secretSocketId"] = sock
        return await self._raw_call("POST", url, body, app_id)

    async def close(self) -> None:
        if self.context:
            await self.context.close()
            self.context = None
            self.page = None
```

What's omitted from this skeleton (but needed in production, mirroring
client.js): bounded request queue with concurrency 1, 15s per-evaluate
timeout, 30s wall-clock budget across retries, 401/403 session recovery,
429/503 exponential backoff. ~150 more lines, mechanical translation.

### 10.4 First-run UX

A new sub-command for login:

```python
# src/internal_api/cli.py
@app.command()
def login(headless: bool = False):
    """Open Airtable in a real browser window for login. Profile persists."""
    auth = AirtableInternalAuth(headless=headless)
    asyncio.run(auth.init())
    print("Logged in. Profile saved to", auth.profile_dir)
```

Subsequent runs use the persisted profile headlessly.

## 11. Implementation sketch — `myairtable push`

The schema-diff command. This is what would make myAirtable a full schema
management tool rather than a one-way generator.

### 11.1 Conceptual flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Code source    │    │   Plan diff      │    │  Apply via      │
│  of truth       │ ─► │   (dry run)      │ ─► │  internal API   │
│  (Python ORM    │    │   show creates,  │    │  with safety    │
│  classes)       │    │   renames, etc.  │    │  guards         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 11.2 What "code source of truth" means

myAirtable already has the inverse: it reads Airtable schema and emits
Python classes. For `push`, we need the user-authored Python to be parseable
back into a normalized schema description. Two options:

- **Decorate generated code** so users edit it in place; the next `push` reads
  decorators back. Brittle if users rearrange code.
- **A new `Base.from_python_models(...)` reflection pass** that walks classes
  decorated with `@table` / `@field(type=..., options=...)` and produces a
  `BaseMetadata` shape comparable to the live one.

I'd start with the second — a tiny declarative DSL on top of the existing
ORM model layer.

### 11.3 Diff algorithm

```python
# src/internal_api/diff.py
from dataclasses import dataclass

@dataclass(frozen=True)
class TableCreate:
    name: str

@dataclass(frozen=True)
class TableRename:
    table_id: str
    old_name: str
    new_name: str

@dataclass(frozen=True)
class TableDestroy:
    table_id: str
    name: str  # for safety check + dry-run output

@dataclass(frozen=True)
class FieldCreate:
    table_id: str
    name: str
    type: str
    type_options: dict

@dataclass(frozen=True)
class FieldRename:
    field_id: str
    old_name: str
    new_name: str

@dataclass(frozen=True)
class FieldUpdateConfig:
    field_id: str
    type: str
    type_options: dict

@dataclass(frozen=True)
class FieldDestroy:
    field_id: str
    name: str
    has_dependents: bool  # populated from precheck

# ...

def plan(desired: BaseSpec, current: BaseMetadata) -> list[Operation]:
    """Return an ordered list of operations to make `current` match `desired`."""
    ops: list[Operation] = []
    # 1. Pair tables by id (if known) or by name
    # 2. Pair fields within tables by id or name
    # 3. Emit creates/destroys/renames/updates
    # 4. Topologically sort: creates before references, destroys after
    # 5. Surface conflicts (renaming a field whose old name is also taken
    #    elsewhere) for user resolution
    return ops
```

Ordering matters: a rollup field that references field B can't be created
until B exists; a field can't be destroyed if a formula still references it
(the `column/destroy` precheck will tell us).

### 11.4 CLI surface

```python
# main.py addition
@app.command()
def push(
    spec: Path = Argument(..., help="Path to Python file with @table-decorated classes"),
    plan_only: bool = Option(False, "--plan", help="Show diff, do not apply"),
    yes: bool = Option(False, "-y", help="Skip confirmation"),
    allow_destructive: bool = Option(False, help="Allow field/table destroy operations"),
):
    """Push schema changes from Python source-of-truth back to Airtable."""
    desired = load_spec(spec)
    current = AirtableInternalClient().get_application_data(get_base_id())
    operations = plan(desired, current)

    print_plan(operations)
    if plan_only:
        return

    destructive = [op for op in operations if isinstance(op, (TableDestroy, FieldDestroy))]
    if destructive and not allow_destructive:
        print("[red]Destructive ops require --allow-destructive.[/]")
        return

    if not yes and not confirm("Apply?"):
        return

    apply(operations)
```

### 11.5 Safety guards (mirror what client.js already does)

- Every `FieldDestroy` / `TableDestroy` runs the dependency precheck first;
  if dependents exist, the plan output shows them and bails unless
  `--force`. The reference client's `summarizeFieldDependencies` is the
  template.
- `expectedName` safety guard on every destroy.
- All payloads run through `validate_formula` first if they touch a formula
  field.
- All operations idempotent — re-running `push` after a partial failure must
  not double-apply.
- Apply runs serially (not in parallel) — Airtable's internal API tolerates
  concurrency, but causality between dependent operations is easier to
  reason about serially.

## 12. Implementation sketch — formula refactoring CLI

This pairs the existing formula tooling with `validate_formula` +
`updateFieldConfig`. Less ambitious than `push`, smaller blast radius.

```bash
# format every formula in the base in place
myairtable formula format --apply

# inline a helper formula into all consumers, then delete it
myairtable formula flatten fldHelper --apply

# rename a field, rewriting every formula reference
myairtable formula rename-field fldOld "New Name" --apply
```

Each command:

1. Reads the schema (public API or cached internal).
2. Computes the new formula text using `formula_formatter` /
   `formula_flattener` / `formula_sanitizer` (already in
   `src/formulas/*.py`).
3. Validates each new formula via
   `POST /v0.3/table/{tableId}/getUnsavedColumnConfigResultType`.
4. Applies via `POST /v0.3/column/{fldId}/updateConfig` with
   `{ type: "formula", typeOptions: { formulaText: <new> } }` (flat payload).
5. Reports diff + result counts.

Failure mode for any single formula = surface and continue. A bad formula
shouldn't stop the batch.

## 13. Recommended phasing

A staged rollout that preserves CI-friendliness for existing users while
unlocking new capabilities:

1. **Phase 1 — Read-only enrichment (low risk).** Add `src/internal_api/`
   with auth + read endpoints (`getApplicationData`, `readTableData`).
   Wire into `markdown` and `html` generators behind a
   `--with-internal-state` flag. No CI impact for users who don't opt in.
2. **Phase 2 — MCP tools.** Add `validate_formula`, `get_view`,
   `get_view_sections`, `get_field_dependencies` to `mcp_server.py`. Pure
   additions; doesn't change existing tool behavior.
3. **Phase 3 — Codegen integration.** Emit typed view constants with filter
   formulas in Python/TS/JS/Rust. Behind a flag initially; default-on once
   stable.
4. **Phase 4 — `myairtable push --plan`.** Plan-only first, no mutations.
   This is where most of the design effort goes — the diff algorithm and
   the Python ORM-as-source-of-truth DSL.
5. **Phase 5 — `myairtable push --apply`.** Mutations behind
   `--allow-destructive`, with thorough integration tests against a
   throwaway base.
6. **Phase 6 — formula refactoring CLI.** Smaller surface than `push`, can
   ship in parallel with phase 5.
7. **(Skip)** Extension management, form metadata. Out of scope.

Phases 1–3 are pure additive value. Phase 4 onwards is a product pivot
worth deliberating before committing.

---

## 14. Source files in the reference implementation

For when `client.js`'s comments need re-reading:

- `packages/mcp-server/src/auth.js` — session, CSRF, `secretSocketId` capture,
  request queue, retry/recovery. ~570 lines.
- `packages/mcp-server/src/client.js` — every endpoint listed in Part 1, with
  inline comments dating the captured traffic and the workarounds. ~1880
  lines.
- `packages/mcp-server/src/tool-config.js` — MCP tool ↔ client method
  mapping.
- `packages/mcp-server/src/index.js` — MCP server entry; tool definitions.

Repo:
[`Automations-Project/VSCode-Airtable-Formula`](https://github.com/Automations-Project/VSCode-Airtable-Formula).
