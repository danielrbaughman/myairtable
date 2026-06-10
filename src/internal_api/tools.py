"""Tool implementations over the internal API.

These are the single source of truth for tool behavior — the CLI commands
(`myairtable tools ...`) and the MCP tools register thin adapters over the
functions in this module. Logic lives here only.

All functions return plain JSON-serializable data and raise InternalApiError
subclasses on failure (adapters convert those to structured error output).
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

from src.meta import get_base_id

from .errors import InternalApiError
from .ids import validate_airtable_id
from .models import (
    InterfaceBundle,
    ShareInfo,
    TableViews,
    ViewDefinition,
    WorkflowSection,
    WorkflowSummary,
    parse_table_views,
    parse_view_definition,
)
from .transport import InternalApiTransport

# application/read is heavy-ish (~MBs on large bases); the schema barely
# changes between consecutive tool calls, so cache briefly.
_SCHEMA_CACHE_TTL_SECONDS = 30.0

# Per-view definitions: there is NO batch endpoint (includeDataForViewIds is
# single-view only — see docs, "Investigation 2026-06-10"), so all-views scans
# are one GET per view. Cache longer than the schema and fetch concurrently.
_VIEW_CACHE_TTL_SECONDS = 120.0
_FETCH_CONCURRENCY = 6

# Automation configs change rarely and a whole-base read is ~1 call/workflow;
# cache the derived reference index longer than the view cache.
_AUTOMATION_INDEX_TTL_SECONDS = 300.0

_transport: InternalApiTransport | None = None
_schema_cache: tuple[float, "ApplicationData"] | None = None
_view_cache: dict[str, tuple[float, ViewDefinition]] = {}
_automation_index_cache: tuple[float, "AutomationReferenceIndex"] | None = None


def _get_transport() -> InternalApiTransport:
    global _transport
    if _transport is None:
        _transport = InternalApiTransport()
    return _transport


class ApplicationData(NamedTuple):
    tables: list[TableViews]
    base_shares: list[ShareInfo]
    interfaces: list[InterfaceBundle]
    workflow_sections: list[WorkflowSection]


def _read_application_data(force_refresh: bool = False) -> ApplicationData:
    """Base schema (view slice) + base-level shares + interfaces, via application/read. Cached for 30s."""
    global _schema_cache
    now = time.monotonic()
    if not force_refresh and _schema_cache is not None and now - _schema_cache[0] < _SCHEMA_CACHE_TTL_SECONDS:
        return _schema_cache[1]

    base_id = validate_airtable_id(get_base_id())
    # The two may* flags are REQUIRED (500 without them); empty
    # includeDataForTableIds keeps the response schema-only JSON.
    payload = _get_transport().get(
        f"/v0.3/application/{base_id}/read",
        object_params={
            "includeDataForTableIds": [],
            "includeDataForViewIds": None,
            "shouldIncludeSchemaChecksum": False,
            "mayOnlyIncludeRowAndCellDataForIncludedViews": True,
            "mayExcludeCellDataForLargeViews": True,
        },
        app_id=base_id,
    )
    data = payload.get("data") or {}
    table_schemas = data.get("tableSchemas")
    if not isinstance(table_schemas, list):
        raise InternalApiError("application/read response has no data.tableSchemas list.")
    tables = [parse_table_views(t) for t in table_schemas]
    base_shares = [ShareInfo.model_validate(s) for s in (data.get("sharesById") or {}).values()]
    interfaces = [InterfaceBundle.model_validate(pb) for pb in (data.get("pageBundles") or [])]
    workflow_sections = [WorkflowSection.model_validate(ws) for ws in (data.get("workflowSectionsById") or {}).values()]
    app_data = ApplicationData(tables, base_shares, interfaces, workflow_sections)
    _schema_cache = (now, app_data)
    return app_data


def _read_table_views(force_refresh: bool = False) -> list[TableViews]:
    return _read_application_data(force_refresh).tables


def _find_table_views(table: str) -> TableViews:
    tables = _read_table_views()
    needle = table.strip().lower()
    for t in tables:
        if t.id == table or t.name.lower() == needle:
            return t
    available = ", ".join(t.name for t in tables)
    raise InternalApiError(f"Table '{table}' not found. Available tables: {available}")


def _find_view(table_views: TableViews, view: str) -> str:
    needle = view.strip().lower()
    for v in table_views.views:
        if v.id == view or v.name.lower() == needle:
            return v.id
    available = ", ".join(v.name for v in table_views.views)
    raise InternalApiError(f"View '{view}' not found in table '{table_views.name}'. Available views: {available}")


def _fetch_view_definition(table_views: TableViews, view_id: str) -> ViewDefinition:
    """One view's definition via view/{viwId}/readData, with TTL cache.

    Name/description are attached from the schema (readData omits them).
    """
    now = time.monotonic()
    cached = _view_cache.get(view_id)
    if cached is not None and now - cached[0] < _VIEW_CACHE_TTL_SECONDS:
        return cached[1]

    base_id = validate_airtable_id(get_base_id())
    payload = _get_transport().get(
        f"/v0.3/view/{validate_airtable_id(view_id)}/readData",
        object_params={},
        app_id=base_id,
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise InternalApiError(f"view/{view_id}/readData response has no data object.")

    definition = parse_view_definition(data)
    info = next((v for v in table_views.views if v.id == view_id), None)
    if info is not None:
        definition.name = info.name
        if definition.description is None:
            definition.description = info.description

    _view_cache[view_id] = (now, definition)
    return definition


def get_all_view_definitions(table_views: TableViews) -> tuple[dict[str, ViewDefinition], dict[str, str]]:
    """Definitions for every view of a table, fetched concurrently.

    There is no batch endpoint — this is one GET per (uncached) view, bounded
    at _FETCH_CONCURRENCY. Returns (definitions_by_view_id, errors_by_view_id);
    individual view failures don't fail the scan.
    """
    definitions: dict[str, ViewDefinition] = {}
    errors: dict[str, str] = {}

    def fetch(view_id: str) -> None:
        try:
            definitions[view_id] = _fetch_view_definition(table_views, view_id)
        except InternalApiError as e:
            errors[view_id] = str(e)

    view_ids = [v.id for v in table_views.views]
    with ThreadPoolExecutor(max_workers=_FETCH_CONCURRENCY) as pool:
        list(pool.map(fetch, view_ids))
    return definitions, errors


def get_view(table: str, view: str) -> dict[str, Any]:
    """Full live definition of a view: filters, sorts, grouping, column
    order/visibility, frozen columns, color config, row height, row count.

    Table and view can be referenced by name (case-insensitive) or ID.
    Uses GET /v0.3/view/{viwId}/readData (spike-discovered endpoint that
    returns the view definition without any cell data).
    """
    table_views = _find_table_views(table)
    view_id = _find_view(table_views, view)
    definition = _fetch_view_definition(table_views, view_id)

    result = definition.model_dump(mode="json", exclude={"shares_by_id"})  # shares belong to audit_shares
    result["table_id"] = table_views.id
    result["table_name"] = table_views.name
    return result


def _find_column(table_views: TableViews, field: str):
    needle = field.strip().lower()
    for c in table_views.columns:
        if c.id == field or c.name.lower() == needle:
            return c
    available = ", ".join(c.name for c in table_views.columns)
    raise InternalApiError(f"Field '{field}' not found in table '{table_views.name}'. Available fields: {available}")


def _filter_operators_for_field(definition: ViewDefinition, field_id: str) -> list[str]:
    """Operators of every filter (incl. inside nested groups) targeting the field."""
    operators: list[str] = []

    def walk(filter_set) -> None:
        for f in filter_set:
            if f.is_nested and f.filter_set:
                walk(f.filter_set)
            elif f.column_id == field_id:
                operators.append(f.operator or "?")

    if definition.filters is not None:
        walk(definition.filters.filter_set)
    return operators


def find_views_using_field(table: str, field: str) -> dict[str, Any]:
    """Which views reference a field — in filters, sorts, grouping, or color
    config — plus where the field is visible vs hidden.

    The view-side complement of reverse_dependencies (which covers formulas):
    together they answer "what breaks if I change this field?".

    Scans every view of the table (one request per uncached view).
    """
    t = _find_table_views(table)
    column = _find_column(t, field)
    definitions, scan_errors = get_all_view_definitions(t)

    views_using: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    visible_in = 0
    hidden_in = 0

    for view_id, d in sorted(definitions.items(), key=lambda kv: (kv[1].name or "")):
        usage: list[dict[str, Any]] = []

        operators = _filter_operators_for_field(d, column.id)
        if operators:
            usage.append({"kind": "filter", "operators": operators})

        if d.last_sorts_applied is not None:
            for s in d.last_sorts_applied.sort_set:
                if s.column_id == column.id:
                    usage.append({"kind": "sort", "ascending": s.ascending})

        for g in d.group_levels or []:
            if g.column_id == column.id:
                usage.append({"kind": "group", "order": g.order})

        # colorConfig shapes vary by type (selectColumn, ...); detect by id presence
        if d.color_config and column.id in str(d.color_config):
            usage.append({"kind": "color"})

        entry = next((c for c in d.column_order if c.column_id == column.id), None)
        if entry is not None:
            visible_in += 1 if entry.visibility else 0
            hidden_in += 0 if entry.visibility else 1

        if usage:
            for u in usage:
                by_kind[u["kind"]] = by_kind.get(u["kind"], 0) + 1
            views_using.append(
                {
                    "id": view_id,
                    "name": d.name,
                    "type": d.type,
                    "usage": usage,
                    "field_visible": entry.visibility if entry else None,
                }
            )

    result: dict[str, Any] = {
        "table_id": t.id,
        "table_name": t.name,
        "field": {"id": column.id, "name": column.name, "type": column.type},
        "summary": {
            "views_scanned": len(definitions),
            "views_using_field": len(views_using),
            "by_kind": by_kind,
            "visible_in": visible_in,
            "hidden_in": hidden_in,
        },
        "views": views_using,
    }
    if scan_errors:
        result["scan_errors"] = scan_errors
    return result


def _has_active_filters(definition: ViewDefinition) -> bool:
    return definition.filters is not None and len(definition.filters.filter_set) > 0


def count_records(table: str, view: str | None = None) -> dict[str, Any]:
    """Record counts from view rowOrder lengths — no record data is downloaded.

    With a view: that view's count (records matching its filters). Without:
    every view's count plus a table total. The total is exact when the table
    has at least one unfiltered view (its rowOrder covers all records);
    otherwise it is the max across views, a lower bound.
    """
    t = _find_table_views(table)

    if view is not None:
        view_id = _find_view(t, view)
        d = _fetch_view_definition(t, view_id)
        return {
            "table_id": t.id,
            "table_name": t.name,
            "view": {"id": view_id, "name": d.name, "type": d.type},
            "row_count": d.row_count,
            "is_filtered": _has_active_filters(d),
        }

    definitions, scan_errors = get_all_view_definitions(t)
    views = []
    unfiltered_counts: list[int] = []
    all_counts: list[int] = []
    for view_id, d in sorted(definitions.items(), key=lambda kv: (kv[1].name or "")):
        if d.row_count is None:
            continue  # form views have no rowOrder
        views.append(
            {
                "id": view_id,
                "name": d.name,
                "type": d.type,
                "row_count": d.row_count,
                "is_filtered": _has_active_filters(d),
            }
        )
        all_counts.append(d.row_count)
        if not _has_active_filters(d):
            unfiltered_counts.append(d.row_count)

    total = max(unfiltered_counts, default=None)
    result: dict[str, Any] = {
        "table_id": t.id,
        "table_name": t.name,
        "total_records": total if total is not None else max(all_counts, default=None),
        "total_is_exact": total is not None,
        "views": views,
    }
    if scan_errors:
        result["scan_errors"] = scan_errors
    return result


# Name patterns that usually indicate abandoned/duplicate views. Extend freely.
SUSPICIOUS_NAME_PATTERNS: list[tuple[str, str]] = [
    (r"\bcopy(\s+\d+)?\b", "copy"),
    (r"\bcopy of\b", "copy of"),
    (r"\btest\b", "test"),
    (r"\buntitled\b", "untitled"),
    (r"\btmp\b|\btemp\b", "temp"),
    (r"\bold\b", "old"),
    (r"\bdraft\b", "draft"),
    (r"\bbackup\b|\bbak\b", "backup"),
    (r"\bdeprecated\b", "deprecated"),
    (r"\(\d+\)\s*$", "numbered duplicate"),
]


def _suspicious_name(name: str) -> str | None:
    for pattern, label in SUSPICIOUS_NAME_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return label
    return None


def audit_views(table: str | None = None, stale_sort_months: int = 6) -> dict[str, Any]:
    """View hygiene report: personal views, suspicious names, unfiltered
    grid duplicates, stale sorts, empty views.

    Scoped to one table, or the whole base if omitted (one request per
    uncached view — a large base takes a while on a cold cache).
    Flags are evidence, not verdicts: a flagged view may be intentional.
    """
    tables = [_find_table_views(table)] if table else _read_table_views()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * stale_sort_months)

    table_reports: list[dict[str, Any]] = []
    kind_totals: dict[str, int] = {}
    total_scanned = 0
    all_scan_errors: dict[str, str] = {}

    for t in tables:
        definitions, scan_errors = get_all_view_definitions(t)
        all_scan_errors.update(scan_errors)
        total_scanned += len(definitions)

        default_grid_id = next((v.id for v in t.views if v.type == "grid"), None)
        flagged: list[dict[str, Any]] = []

        for info in t.views:
            d = definitions.get(info.id)
            flags: list[dict[str, Any]] = []

            if info.personal_for_user_id:
                flags.append({"kind": "personal", "owner_user_id": info.personal_for_user_id})

            label = _suspicious_name(info.name)
            if label:
                flags.append({"kind": "suspicious_name", "matched": label})

            if d is not None:
                if d.type == "grid" and info.id != default_grid_id and not _has_active_filters(d):
                    flags.append({"kind": "unfiltered_grid", "note": "no filters — possibly a duplicate of the default view"})

                applied = d.last_sorts_applied.applied_time if d.last_sorts_applied else None
                if applied:
                    try:
                        applied_dt = datetime.fromisoformat(applied.replace("Z", "+00:00"))
                        if applied_dt < cutoff:
                            flags.append({"kind": "stale_sort", "applied_time": applied})
                    except ValueError:
                        pass

                if d.row_count == 0:
                    flags.append({"kind": "empty"})

            if flags:
                for f in flags:
                    kind_totals[f["kind"]] = kind_totals.get(f["kind"], 0) + 1
                flagged.append(
                    {
                        "id": info.id,
                        "name": info.name,
                        "type": info.type,
                        "created_by_user_id": (d.created_by_user_id if d else None) or info.created_by_user_id,
                        "flags": flags,
                    }
                )

        if flagged:
            table_reports.append({"table_id": t.id, "table_name": t.name, "views_flagged": flagged})

    result: dict[str, Any] = {
        "summary": {
            "tables_scanned": len(tables),
            "views_scanned": total_scanned,
            "views_flagged": sum(len(r["views_flagged"]) for r in table_reports),
            "by_kind": kind_totals,
            "stale_sort_months": stale_sort_months,
        },
        "tables": table_reports,
    }
    if all_scan_errors:
        result["scan_errors"] = all_scan_errors
    return result


_UNUSED_FIELD_CAVEATS = [
    "Usage by automations, interfaces, sync targets, and external API consumers is NOT visible to this analysis.",
    "Signals are independent evidence, not a deletion verdict — verify before removing anything.",
    "Computed fields (formula/lookup/rollup/count) and linked-record fields are excluded: they are consumers or structural.",
]


def _collect_view_field_usage(definitions: dict[str, ViewDefinition]) -> dict[str, dict[str, int]]:
    """Per field id: visible_in / present_in (columnOrder) and config_uses (filter/sort/group/color)."""
    usage: dict[str, dict[str, int]] = {}

    def bump(field_id: str, key: str) -> None:
        u = usage.setdefault(field_id, {"present_in": 0, "visible_in": 0, "config_uses": 0})
        u[key] += 1

    for d in definitions.values():
        for entry in d.column_order:
            bump(entry.column_id, "present_in")
            if entry.visibility:
                bump(entry.column_id, "visible_in")

        def walk(filter_set) -> None:
            for f in filter_set:
                if f.is_nested and f.filter_set:
                    walk(f.filter_set)
                elif f.column_id:
                    bump(f.column_id, "config_uses")

        if d.filters is not None:
            walk(d.filters.filter_set)
        if d.last_sorts_applied is not None:
            for s in d.last_sorts_applied.sort_set:
                bump(s.column_id, "config_uses")
        for g in d.group_levels or []:
            bump(g.column_id, "config_uses")
        if d.color_config:
            blob = str(d.color_config)
            for field_id in usage:
                if field_id in blob:
                    bump(field_id, "config_uses")

    return usage


def find_unused_fields(table: str | None = None, min_signals: int = 2) -> dict[str, Any]:
    """Candidate-unused fields, combining public-API formula analysis with
    internal-API view usage.

    Three independent signals per field:
    - no_formula_references (public meta API): not referenced by any formula,
      lookup, rollup, or link configuration anywhere in the base
    - hidden_in_all_views (internal): present in view columnOrders but visible
      in none
    - not_in_view_config (internal): used by no view filter/sort/group/color

    Fields reaching min_signals are reported with all evidence. This is a
    lead-generator, not a verdict — see the caveats in the output.
    """
    from src.meta import Base

    base = Base()  # public meta API — formula/lookup/rollup reference graph
    referenced_ids: set[str] = set()
    for field in base.fields():
        if field.options and field.options.referenced_field_ids:
            referenced_ids.update(field.options.referenced_field_ids)
        if field.options and field.options.field_id_in_linked_table:
            referenced_ids.add(field.options.field_id_in_linked_table)
        if field.options and field.options.record_link_field_id:
            referenced_ids.add(field.options.record_link_field_id)
        if field.is_formula():
            referenced_ids.update(field.get_field_ids_from_formula())

    public_fields_by_table_id = {t.id: t.fields for t in base.tables}

    internal_tables = [_find_table_views(table)] if table else _read_table_views()

    reported: list[dict[str, Any]] = []
    fields_scanned = 0
    all_scan_errors: dict[str, str] = {}

    for t in internal_tables:
        public_fields = public_fields_by_table_id.get(t.id)
        if public_fields is None:
            continue  # table not visible to the public API (shouldn't happen)
        definitions, scan_errors = get_all_view_definitions(t)
        all_scan_errors.update(scan_errors)
        usage = _collect_view_field_usage(definitions)

        for field in public_fields:
            if field.is_computed() or field.type == "multipleRecordLinks":
                continue
            if field.id == t.primary_column_id:
                continue  # structural
            fields_scanned += 1

            u = usage.get(field.id, {"present_in": 0, "visible_in": 0, "config_uses": 0})
            signals: list[str] = []
            if field.id not in referenced_ids:
                signals.append("no_formula_references")
            if u["present_in"] > 0 and u["visible_in"] == 0:
                signals.append("hidden_in_all_views")
            if u["config_uses"] == 0:
                signals.append("not_in_view_config")

            if len(signals) >= min_signals:
                reported.append(
                    {
                        "table_id": t.id,
                        "table_name": t.name,
                        "id": field.id,
                        "name": field.name,
                        "type": field.type,
                        "signals": signals,
                        "evidence": {
                            "visible_in_views": u["visible_in"],
                            "present_in_views": u["present_in"],
                            "view_config_uses": u["config_uses"],
                        },
                    }
                )

    reported.sort(key=lambda f: (-len(f["signals"]), f["table_name"], f["name"]))
    result: dict[str, Any] = {
        "summary": {
            "tables_scanned": len(internal_tables),
            "fields_scanned": fields_scanned,
            "fields_reported": len(reported),
            "min_signals": min_signals,
        },
        "fields": reported,
        "caveats": _UNUSED_FIELD_CAVEATS,
    }
    if all_scan_errors:
        result["scan_errors"] = all_scan_errors
    return result


def _share_entry(share: ShareInfo, scope: str, table: TableViews | None = None, view_name: str | None = None) -> dict[str, Any]:
    return {
        "id": share.id,
        "url": f"https://airtable.com/{share.id}",
        "scope": scope,
        "table_id": table.id if table else None,
        "table_name": table.name if table else None,
        "view_id": share.model_id if scope == "view" else None,
        "view_name": view_name,
        "created_by_user_id": share.created_by_user_id,
        "can_be_exported": share.can_be_exported,
        "can_be_cloned": share.can_be_cloned,
        "include_hidden_columns": share.include_hidden_columns,
        "include_blocks": share.include_blocks,
        "has_password": share.has_password,
        "email_domain": share.email_domain,
    }


def audit_shares(table: str | None = None) -> dict[str, Any]:
    """Every share link in the base (or one table's views), with what each
    exposes.

    A share id (shr...) is a public URL token — anyone holding
    https://airtable.com/{shrId} can see the shared data, subject only to the
    password/domain restrictions reported here. Base-level shares expose the
    whole base; view shares expose one view's records.
    """
    app_data = _read_application_data()
    all_tables, base_shares = app_data.tables, app_data.base_shares
    tables = [_find_table_views(table)] if table else all_tables

    shares: list[dict[str, Any]] = []
    if table is None:
        shares.extend(_share_entry(s, "base") for s in base_shares)

    all_scan_errors: dict[str, str] = {}
    views_scanned = 0
    for t in tables:
        definitions, scan_errors = get_all_view_definitions(t)
        all_scan_errors.update(scan_errors)
        views_scanned += len(definitions)
        for view_id, d in sorted(definitions.items(), key=lambda kv: (kv[1].name or "")):
            for share in d.shares_by_id.values():
                shares.append(_share_entry(share, "view", table=t, view_name=d.name))

    result: dict[str, Any] = {
        "summary": {
            "total_shares": len(shares),
            "base_shares": sum(1 for s in shares if s["scope"] == "base"),
            "view_shares": sum(1 for s in shares if s["scope"] == "view"),
            "exportable": sum(1 for s in shares if s["can_be_exported"]),
            "password_protected": sum(1 for s in shares if s["has_password"]),
            "domain_restricted": sum(1 for s in shares if s["email_domain"]),
            "views_scanned": views_scanned,
        },
        "shares": shares,
    }
    if all_scan_errors:
        result["scan_errors"] = all_scan_errors
    return result


def list_interfaces() -> dict[str, Any]:
    """All interfaces (page bundles) in the base, with pages and publish state.

    Interfaces are invisible to the public API entirely — this is the only
    programmatic inventory. Comes from the already-cached application/read
    response, so it's a single (often zero) network call.
    """
    app_data = _read_application_data()
    base_id = get_base_id()

    interfaces = []
    for bundle in app_data.interfaces:
        pages = [
            {
                "id": p.id,
                "name": (p.metadata.name if p.metadata else None) or "Untitled",
                "is_published": p.is_published,
                "last_published": p.last_published_revision_change_time,
                "last_draft_modified": p.last_working_draft_modified_time,
            }
            for p in bundle.pages
        ]
        interfaces.append(
            {
                "id": bundle.id,
                "name": bundle.name,
                "description": bundle.description,
                "icon": bundle.icon,
                "color": bundle.color,
                "url": f"https://airtable.com/{base_id}/{bundle.id}",
                "is_published": any(p["is_published"] for p in pages),
                "first_page_published_time": bundle.first_page_published_time,
                "last_published_time": bundle.last_published_time,
                "pages": pages,
            }
        )

    return {
        "summary": {
            "interfaces": len(interfaces),
            "published": sum(1 for i in interfaces if i["is_published"]),
            "pages": sum(len(i["pages"]) for i in interfaces),
        },
        "interfaces": interfaces,
    }


# Known workflow trigger/action type-id constants → friendly names. Opaque
# hash ids (integration/first-party-app types) are passed through verbatim.
_WORKFLOW_TYPE_NAMES = {
    "wttRECORDMATCHES0": "When record matches conditions",
    "wttRECORDCREATED0": "When record created",
    "wttRECORDUPDATED0": "When record updated",
    "wttRECORDENTERSVIEW": "When record enters view",
    "wttCRON0000000000": "At scheduled time",
    "wttFORMSUBMITTED0": "When form submitted",
    "wttBUTTONCLICKED0": "When button clicked",
    "watUPDATERECORD00": "Update record",
    "watCREATERECORD00": "Create record",
    "watFINDRECORDS000": "Find records",
    "watGMAILSENDMAIL0": "Send email (Gmail)",
    "watSENDEMAIL00000": "Send email",
    "watCUSTOMSCRIPT00": "Run script",
    "watSLACKMESSAGE00": "Send Slack message",
}

_ID_REF_RE = re.compile(r'"(tbl|fld)([A-Za-z0-9]{14})"')


def _type_name(type_id: str | None) -> str | None:
    if type_id is None:
        return None
    return _WORKFLOW_TYPE_NAMES.get(type_id, type_id)


def _refs_in_blob(config: Any) -> tuple[set[str], set[str]]:
    """(table_ids, field_ids) referenced in one config object."""
    blob = json.dumps(config)
    tables = {f"tbl{m}" for p, m in _ID_REF_RE.findall(blob) if p == "tbl"}
    fields = {f"fld{m}" for p, m in _ID_REF_RE.findall(blob) if p == "fld"}
    return tables, fields


def _extract_id_refs(config: Any) -> dict[str, list[str]]:
    """Table/field IDs referenced anywhere in a workflow config blob."""
    tables, fields = _refs_in_blob(config)
    return {"table_ids": sorted(tables), "field_ids": sorted(fields)}


def _workflow_detail(wfl_id: str) -> dict[str, Any]:
    """Full config of one workflow via workflow/{id}/read.

    Envelope (id/name/trigger type/action list) is structured; action and
    trigger configs (inputExpressions) pass through as raw JSON — they are
    open-ended (custom scripts, integration actions) and not worth modeling.
    """
    base_id = validate_airtable_id(get_base_id())
    payload = _get_transport().get(
        f"/v0.3/workflow/{validate_airtable_id(wfl_id)}/read",
        object_params={},
        app_id=base_id,
    )
    wf = (payload.get("data") or {}).get("workflow")
    if not isinstance(wf, dict):
        raise InternalApiError(f"workflow/{wfl_id}/read response has no data.workflow object.")

    trigger = wf.get("trigger") or {}
    graph = wf.get("graph") or {}
    actions_by_id = graph.get("actionsById") or {}

    # Walk the action chain from the entry point so order is meaningful.
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = graph.get("entryWorkflowActionId")
    while current and current in actions_by_id and current not in seen:
        seen.add(current)
        a = actions_by_id[current]
        actions.append(
            {
                "id": a.get("id"),
                "type_id": a.get("workflowActionTypeId"),
                "type": _type_name(a.get("workflowActionTypeId")),
                "config": a.get("inputExpressions"),
            }
        )
        current = a.get("nextWorkflowActionId")
    # Include any actions not reachable from the entry chain (branches, orphans).
    for aid, a in actions_by_id.items():
        if aid not in seen:
            actions.append(
                {
                    "id": a.get("id"),
                    "type_id": a.get("workflowActionTypeId"),
                    "type": _type_name(a.get("workflowActionTypeId")),
                    "config": a.get("inputExpressions"),
                }
            )

    return {
        "trigger": {
            "type_id": trigger.get("workflowTriggerTypeId"),
            "type": _type_name(trigger.get("workflowTriggerTypeId")),
            "config": trigger.get("inputExpressions"),
        },
        "actions": actions,
        "references": _extract_id_refs(wf),
    }


def list_automations(workflow: str | None = None, include_config: bool = True) -> dict[str, Any]:
    """All automations (workflows), organized by sidebar section, with full
    trigger/action configuration.

    Automations have no public API at all. With include_config (default), each
    workflow's full trigger and action configs are dumped (one extra request
    per workflow — concurrent). Pass `workflow` (name or wfl ID) to dump just
    one. Referenced table/field IDs are extracted from each config.
    """
    base_id = validate_airtable_id(get_base_id())
    app_data = _read_application_data()

    payload = _get_transport().get(
        f"/v0.3/application/{base_id}/listWorkflows",
        object_params={},
        app_id=base_id,
    )
    raw = (payload.get("data") or {}).get("workflows")
    if not isinstance(raw, list):
        raise InternalApiError("listWorkflows response has no data.workflows list.")
    summaries = [WorkflowSummary.model_validate(w) for w in raw]
    by_id = {w.id: w for w in summaries}

    # Single-workflow mode
    if workflow is not None:
        needle = workflow.strip().lower()
        match = next((w for w in summaries if w.id == workflow or (w.name or "").lower() == needle), None)
        if match is None:
            available = ", ".join(w.name or w.id for w in summaries)
            raise InternalApiError(f"Automation '{workflow}' not found. Available: {available}")
        entry = _workflow_entry(match, include_config=True)
        return {"workflow": entry}

    detail_by_id: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    if include_config:

        def fetch(wfl_id: str) -> None:
            try:
                detail_by_id[wfl_id] = _workflow_detail(wfl_id)
            except InternalApiError as e:
                errors[wfl_id] = str(e)

        with ThreadPoolExecutor(max_workers=_FETCH_CONCURRENCY) as pool:
            list(pool.map(fetch, list(by_id)))

    def entry(w: WorkflowSummary) -> dict[str, Any]:
        return _workflow_entry(w, include_config=include_config, detail=detail_by_id.get(w.id))

    # Organize by section; collect unsectioned workflows after.
    sections: list[dict[str, Any]] = []
    sectioned_ids: set[str] = set()
    for section in app_data.workflow_sections:
        members = [entry(by_id[wid]) for wid in section.workflow_order if wid in by_id]
        sectioned_ids.update(w.id for w in (by_id[wid] for wid in section.workflow_order if wid in by_id))
        sections.append({"id": section.id, "name": section.name, "automations": members})

    ungrouped = [entry(w) for w in summaries if w.id not in sectioned_ids]

    result: dict[str, Any] = {
        "summary": {
            "total": len(summaries),
            "deployed": sum(1 for w in summaries if w.deployment_status == "deployed"),
            "sections": len(sections),
        },
        "sections": sections,
        "ungrouped_automations": ungrouped,
    }
    if errors:
        result["scan_errors"] = errors
    return result


def _workflow_entry(w: WorkflowSummary, include_config: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": w.id,
        "name": w.name,
        "description": w.description,
        "deployment_status": w.deployment_status,
    }
    if include_config:
        if detail is None:
            detail = _workflow_detail(w.id)
        entry.update(detail)
    return entry


class AutomationReferenceIndex(NamedTuple):
    """Base-wide map of which automations reference each field/table.

    fields/tables map an id → list of reference dicts:
      {automation_id, automation_name, deployment_status, where, action_type?}
    where is "trigger" or "action". errors maps wfl_id → message for
    workflows whose config could not be read.
    """

    fields: dict[str, list[dict[str, Any]]]
    tables: dict[str, list[dict[str, Any]]]
    errors: dict[str, str]


def _automation_reference_index(force_refresh: bool = False) -> AutomationReferenceIndex:
    """Build (cached) the field/table → automations map from full workflow configs.

    Base-wide: an automation in any section can reference any table's fields,
    so this can't be scoped down. One read per workflow (concurrent), cached
    for _AUTOMATION_INDEX_TTL_SECONDS.
    """
    global _automation_index_cache
    now = time.monotonic()
    if not force_refresh and _automation_index_cache is not None and now - _automation_index_cache[0] < _AUTOMATION_INDEX_TTL_SECONDS:
        return _automation_index_cache[1]

    base_id = validate_airtable_id(get_base_id())
    payload = _get_transport().get(
        f"/v0.3/application/{base_id}/listWorkflows",
        object_params={},
        app_id=base_id,
    )
    raw = (payload.get("data") or {}).get("workflows")
    if not isinstance(raw, list):
        raise InternalApiError("listWorkflows response has no data.workflows list.")
    summaries = [WorkflowSummary.model_validate(w) for w in raw]

    fields: dict[str, list[dict[str, Any]]] = {}
    tables: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    def add(index: dict[str, list[dict[str, Any]]], ref_id: str, ref: dict[str, Any]) -> None:
        index.setdefault(ref_id, []).append(ref)

    def process(w: WorkflowSummary) -> None:
        try:
            detail = _workflow_detail(w.id)
        except InternalApiError as e:
            errors[w.id] = str(e)
            return
        base_ref = {"automation_id": w.id, "automation_name": w.name, "deployment_status": w.deployment_status}
        sources = [("trigger", None, detail.get("trigger", {}).get("config"))]
        for action in detail.get("actions", []):
            sources.append(("action", action.get("type"), action.get("config")))
        for where, action_type, config in sources:
            tbls, flds = _refs_in_blob(config)
            ref = {**base_ref, "where": where}
            if action_type:
                ref["action_type"] = action_type
            for tid in tbls:
                add(tables, tid, ref)
            for fid in flds:
                add(fields, fid, ref)

    with ThreadPoolExecutor(max_workers=_FETCH_CONCURRENCY) as pool:
        list(pool.map(process, summaries))

    index = AutomationReferenceIndex(fields=fields, tables=tables, errors=errors)
    _automation_index_cache = (now, index)
    return index


def get_view_sections(table: str | None = None) -> list[dict[str, Any]]:
    """Sidebar view sections (groupings) per table, with the views each
    contains and any ungrouped views, in sidebar display order.

    Optionally scoped to one table (by name or ID).
    """
    tables = [_find_table_views(table)] if table else _read_table_views()

    results: list[dict[str, Any]] = []
    for t in tables:
        views_by_id = {v.id: v for v in t.views}

        def _view_entry(view_id: str) -> dict[str, Any] | None:
            v = views_by_id.get(view_id)
            return {"id": v.id, "name": v.name, "type": v.type} if v else None

        sections = []
        grouped_view_ids: set[str] = set()
        for section_id in t.view_order:
            if not section_id.startswith("vsc"):
                continue
            section = t.view_sections_by_id.get(section_id)
            if section is None:
                continue
            member_views = [e for vid in section.view_order if (e := _view_entry(vid))]
            grouped_view_ids.update(v["id"] for v in member_views)
            sections.append({"id": section.id, "name": section.name, "views": member_views})

        ungrouped = [e for vid in t.view_order if vid.startswith("viw") and vid not in grouped_view_ids and (e := _view_entry(vid))]
        results.append(
            {
                "table_id": t.id,
                "table_name": t.name,
                "sections": sections,
                "ungrouped_views": ungrouped,
            }
        )
    return results
