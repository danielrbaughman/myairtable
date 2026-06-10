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
    def find_views_using_field(table_name: str, field_name: str) -> dict:
        """Find every view that references a field — in filters, sorts, grouping, or color config — plus visible/hidden counts across all views.

        The view-side complement of reverse_dependencies (which covers formula references):
        together they answer "what breaks if I change this field?". Scans every view of the
        table (one request per uncached view; ~30 views take a few seconds cold).

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.find_views_using_field(table_name, field_name)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def count_records(table_name: str, view_name: str = "") -> dict:
        """Count records per view (and the table total) WITHOUT downloading any record data.

        Each view's count reflects its filters — effectively saved-query statistics the public
        API cannot provide without paging through all records. total_is_exact is true when the
        table has at least one unfiltered view; otherwise the total is a lower bound (max across
        views). Optionally scope to one view via view_name.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.count_records(table_name, view_name or None)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def audit_views(table_name: str = "", stale_sort_months: int = 6) -> dict:
        """View hygiene report: flags personal views, suspicious names (copy/test/old/...),
        unfiltered grid views (likely duplicates of the default), stale sorts, and empty views.

        Scope to one table via table_name, or scan the whole base if omitted (one request per
        uncached view — a large base takes minutes cold, so prefer per-table scans when iterating).
        Flags are evidence with details, not verdicts.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.audit_views(table_name or None, stale_sort_months=stale_sort_months)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def find_unused_fields(table_name: str = "", min_signals: int = 2) -> dict:
        """Find candidate-unused fields by combining formula analysis (public API) with live view usage (internal API).

        Stronger than find_dead_fields (formula references only): adds whether each field is
        hidden in every view and whether any view filters/sorts/groups/colors by it. Each field
        is reported with its independent signals and evidence — automations, interfaces, and
        external API consumers are NOT visible to this analysis, so treat results as leads,
        never as safe-to-delete verdicts. Scope to one table via table_name (whole base scans
        are one request per uncached view — minutes when cold).

        Uses Airtable's internal (unofficial) API plus the public meta API. Auto-authenticates
        from AIRTABLE_EMAIL / AIRTABLE_PASSWORD in .env. On failure, returns {"error",
        "message"} — public-API tools are unaffected.
        """
        try:
            return tools.find_unused_fields(table_name or None, min_signals=min_signals)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def audit_shares(table_name: str = "") -> dict:
        """List every share link in the base — base-level and per-view — with what each exposes.

        For each share: full public URL, scope, table/view, creator, and exposure flags
        (exportable, cloneable, includes hidden columns, password-protected, domain-restricted).
        A share URL grants access to anyone holding it, so treat output as sensitive. Scope to
        one table via table_name; whole-base scans are one request per uncached view.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.audit_shares(table_name or None)
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def list_interfaces() -> dict:
        """List all interfaces (Airtable's app-builder 'page bundles') in the base: name, icon,
        pages, publish state, and last-published/last-edited times.

        Interfaces are completely invisible to the public API — this is the only programmatic
        inventory. Cheap: served from the cached schema response.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.list_interfaces()
        except InternalApiError as e:
            return _error_payload(e)

    @mcp.tool()
    def list_automations(workflow: str = "", include_config: bool = True) -> dict:
        """List all automations (workflows), organized by sidebar section, with full trigger and action configuration.

        Automations have NO public API — this is the only programmatic access. Each automation
        includes its trigger and ordered actions with friendly type names plus raw config, and
        the table/field IDs it references (a real dependency signal: a field may be load-bearing
        in an automation while looking unused everywhere else). With include_config=true (default)
        this is one extra request per workflow (concurrent); set false for a fast inventory, or
        pass workflow (name or wfl ID) to dump just one.

        Uses Airtable's internal (unofficial) API. Auto-authenticates from AIRTABLE_EMAIL /
        AIRTABLE_PASSWORD in .env. On failure, returns {"error", "message"} — public-API tools
        are unaffected.
        """
        try:
            return tools.list_automations(workflow or None, include_config=include_config)
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
