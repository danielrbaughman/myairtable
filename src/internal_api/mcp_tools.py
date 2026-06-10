"""MCP adapters for the internal-API tools.

Thin adapters only — all logic lives in src/internal_api/tools.py (shared
with the CLI `myairtable tools ...` commands, so CLI testing verifies these).

Failures return structured error payloads instead of raising, so an
internal-API outage (Airtable changing the unofficial v0.3 endpoints, expired
credentials, missing playwright) degrades to an actionable message — the 24
public-API tools are never affected.
"""

from typing import Any

from . import tools
from .errors import InternalApiError


def _error_payload(e: Exception) -> dict[str, Any]:
    return {"error": type(e).__name__, "message": str(e)}


def register(mcp: Any) -> None:
    """Register the internal-API tools onto the given FastMCP instance."""

    @mcp.tool()
    def get_view(table_name: str, view_name: str) -> dict:
        """Get the full live definition of a view: filters, sorts, grouping, column order/visibility, frozen column count, color config.

        Unlike the static view list from describe_table (id/name/type only), this returns what the
        view actually does. Table and view can be referenced by name (case-insensitive) or ID.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected; the message says how to fix it (usually `myairtable login` or .env vars).
        """
        try:
            return tools.get_view(table_name, view_name)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def get_view_sections(table_name: str = "") -> list[dict] | dict:
        """Get sidebar view sections (the named groups views are organized under in Airtable's sidebar) per table, with member views and ungrouped views in display order.

        Optionally scoped to one table by name (case-insensitive) or ID; all tables if omitted.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.get_view_sections(table_name or None)
        except InternalApiError as e:
            return _error_payload(e)
