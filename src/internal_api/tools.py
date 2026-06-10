"""Tool implementations over the internal API.

These are the single source of truth for tool behavior — the CLI commands
(`myairtable tools ...`) and the MCP tools register thin adapters over the
functions in this module. Logic lives here only.

All functions return plain JSON-serializable data and raise InternalApiError
subclasses on failure (adapters convert those to structured error output).
"""

import time
from typing import Any

from src.meta import get_base_id

from .errors import InternalApiError
from .ids import validate_airtable_id
from .models import TableViews, ViewDefinition, parse_table_views, parse_view_definition
from .transport import InternalApiTransport

# application/read is heavy-ish (~MBs on large bases); the schema barely
# changes between consecutive tool calls, so cache briefly.
_SCHEMA_CACHE_TTL_SECONDS = 30.0

_transport: InternalApiTransport | None = None
_schema_cache: tuple[float, list[TableViews]] | None = None


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


def get_view(table: str, view: str) -> dict[str, Any]:
    """Full live definition of a view: filters, sorts, grouping, column
    order/visibility, frozen columns, color config, row height.

    Table and view can be referenced by name (case-insensitive) or ID.
    Uses GET /v0.3/view/{viwId}/readData (spike-discovered endpoint that
    returns the view definition without any cell data).
    """
    table_views = _find_table_views(table)
    view_id = validate_airtable_id(_find_view(table_views, view))
    base_id = validate_airtable_id(get_base_id())

    payload = _get_transport().get(
        f"/v0.3/view/{view_id}/readData",
        object_params={},
        app_id=base_id,
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise InternalApiError(f"view/{view_id}/readData response has no data object.")

    definition: ViewDefinition = parse_view_definition(data)
    # readData does not include the name; attach it from the schema
    info = next(v for v in table_views.views if v.id == view_id)
    definition.name = info.name
    if definition.description is None:
        definition.description = info.description

    result = definition.model_dump(mode="json")
    result["table_id"] = table_views.id
    result["table_name"] = table_views.name
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
