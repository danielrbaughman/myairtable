"""Tool implementations over the internal API.

These are the single source of truth for tool behavior — the CLI commands
(`myairtable tools ...`) and the MCP tools register thin adapters over the
functions in this module. Logic lives here only.

All functions return plain JSON-serializable data and raise InternalApiError
subclasses on failure (adapters convert those to structured error output).
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.meta import get_base_id

from .errors import InternalApiError
from .ids import validate_airtable_id
from .models import TableViews, ViewDefinition, parse_table_views, parse_view_definition
from .transport import InternalApiTransport

# application/read is heavy-ish (~MBs on large bases); the schema barely
# changes between consecutive tool calls, so cache briefly.
_SCHEMA_CACHE_TTL_SECONDS = 30.0

# Per-view definitions: there is NO batch endpoint (includeDataForViewIds is
# single-view only — see docs, "Investigation 2026-06-10"), so all-views scans
# are one GET per view. Cache longer than the schema and fetch concurrently.
_VIEW_CACHE_TTL_SECONDS = 120.0
_FETCH_CONCURRENCY = 6

_transport: InternalApiTransport | None = None
_schema_cache: tuple[float, list[TableViews]] | None = None
_view_cache: dict[str, tuple[float, ViewDefinition]] = {}


def _get_transport() -> InternalApiTransport:
    global _transport
    if _transport is None:
        _transport = InternalApiTransport()
    return _transport


def _read_table_views(force_refresh: bool = False) -> list[TableViews]:
    """Base schema (view slice), via application/read. Cached for 30s."""
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
    table_schemas = (payload.get("data") or {}).get("tableSchemas")
    if not isinstance(table_schemas, list):
        raise InternalApiError("application/read response has no data.tableSchemas list.")
    tables = [parse_table_views(t) for t in table_schemas]
    _schema_cache = (now, tables)
    return tables


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

    result = definition.model_dump(mode="json")
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
