"""CLI adapters for the internal-API tools.

Thin adapters only — all logic lives in src/internal_api/tools.py (shared
with the MCP server, so a CLI invocation verifies MCP behavior too).

Output is JSON on stdout by default (agent-testable, pipeable to jq);
--pretty renders with rich. Failures print a JSON object with an "error" key
and exit 1.
"""

import json
import sys
from typing import Annotated, Any

from rich import print as rich_print
from typer import Argument, Exit, Option, Typer

from . import tools
from .errors import InternalApiError

tools_app = Typer(help="Schema tools (CLI mirrors of the MCP tools). Internal-API backed commands auto-authenticate from .env.")


def _emit(result: Any, pretty: bool) -> None:
    if pretty:
        rich_print(result)
    else:
        print(json.dumps(result, indent=2))


def _fail(error: Exception) -> None:
    print(json.dumps({"error": type(error).__name__, "message": str(error)}, indent=2), file=sys.stderr)
    raise Exit(code=1)


@tools_app.command("get-view")
def get_view_command(
    table: Annotated[str, Argument(help="Table name (case-insensitive) or ID")],
    view: Annotated[str, Argument(help="View name (case-insensitive) or ID")],
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Full live view definition: filters, sorts, grouping, column order/visibility.

    Uses Airtable's internal (unofficial) API; auto-authenticates from
    AIRTABLE_EMAIL / AIRTABLE_PASSWORD in .env.
    """
    try:
        _emit(tools.get_view(table, view), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("find-views-using-field")
def find_views_using_field_command(
    table: Annotated[str, Argument(help="Table name (case-insensitive) or ID")],
    field: Annotated[str, Argument(help="Field name (case-insensitive) or ID")],
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Which views filter/sort/group/color by a field, plus visibility.

    The view-side complement of reverse_dependencies. Scans every view of the
    table (one request per uncached view). Internal (unofficial) API.
    """
    try:
        _emit(tools.find_views_using_field(table, field), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("count-records")
def count_records_command(
    table: Annotated[str, Argument(help="Table name (case-insensitive) or ID")],
    view: Annotated[str, Argument(help="Optional view name or ID; all views if omitted")] = "",
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Record counts per view (and table total) without downloading records.

    Counts reflect each view's filters — saved-query stats the public API
    can't provide without paging. Internal (unofficial) API.
    """
    try:
        _emit(tools.count_records(table, view or None), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("audit-views")
def audit_views_command(
    table: Annotated[str, Argument(help="Optional table name or ID; whole base if omitted")] = "",
    stale_sort_months: Annotated[int, Option(help="Months after which a lastSortsApplied counts as stale")] = 6,
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """View hygiene report: personal views, suspicious names, unfiltered
    duplicates, stale sorts, empty views.

    Whole-base scans are one request per uncached view — expect a wait on a
    cold cache. Internal (unofficial) API.
    """
    try:
        _emit(tools.audit_views(table or None, stale_sort_months=stale_sort_months), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("find-unused-fields")
def find_unused_fields_command(
    table: Annotated[str, Argument(help="Optional table name or ID; whole base if omitted")] = "",
    min_signals: Annotated[int, Option(help="Minimum independent signals (1-3) for a field to be reported")] = 2,
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Candidate-unused fields: no formula refs (public API) + hidden in all
    views + unused in view configs (internal API).

    A lead-generator with explicit caveats, not a deletion verdict.
    """
    try:
        _emit(tools.find_unused_fields(table or None, min_signals=min_signals), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("audit-shares")
def audit_shares_command(
    table: Annotated[str, Argument(help="Optional table name or ID; whole base if omitted")] = "",
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Every share link in the base with its exposure details and full URL.

    Share IDs are public URL tokens — treat this output as sensitive.
    Whole-base scans are one request per uncached view. Internal (unofficial) API.
    """
    try:
        _emit(tools.audit_shares(table or None), pretty)
    except InternalApiError as e:
        _fail(e)


@tools_app.command("get-view-sections")
def get_view_sections_command(
    table: Annotated[str, Argument(help="Optional table name or ID; all tables if omitted")] = "",
    pretty: Annotated[bool, Option("--pretty", help="Rich output instead of plain JSON")] = False,
):
    """Sidebar view sections per table, with member views in display order.

    Uses Airtable's internal (unofficial) API; auto-authenticates from
    AIRTABLE_EMAIL / AIRTABLE_PASSWORD in .env.
    """
    try:
        _emit(tools.get_view_sections(table or None), pretty)
    except InternalApiError as e:
        _fail(e)


def login_command(
    headful: Annotated[bool, Option("--headful", help="Show the browser window (debugging)")] = False,
):
    """Force a fresh Airtable internal-API login (debugging).

    Normal flow never needs this — tools auto-authenticate from .env and the
    session lives ~1 year. Use --headful to watch the scripted login.
    """
    from .auth import STATE_FILE, login
    from .errors import InternalApiError as _Err

    try:
        login(headless=not headful)
        print(json.dumps({"status": "ok", "state_file": str(STATE_FILE)}))
    except _Err as e:
        _fail(e)
