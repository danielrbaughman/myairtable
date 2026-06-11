from __future__ import annotations

import dotenv

dotenv.load_dotenv()

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    "myairtable",
    instructions="""\
Read-only Airtable schema introspection and analysis tools.

Provides 24 tools for exploring an Airtable base without modifying it:

- **Schema browsing**: get_schema, list_tables, describe_table, describe_field, search_fields
- **Relationships**: get_links, get_lookups_and_rollups, check_link_symmetry
- **Formulas**: get_formula, list_formula_fields, flatten_formula, analyze_formula_complexity, transpile, formula_function_usage (base-wide function histogram)
- **Dependencies**: trace_field_dependencies, reverse_dependencies, find_circular_references
- **Validation**: find_invalid_fields, analyze_type_consistency, find_type_ambiguities
- **Statistics**: base_stats, find_dead_fields, compare_tables, get_select_options
- **Graph analysis**: dependency_graph_metrics (per-field blast radius / depth / centrality, base-wide), table_connectivity (link graph: hubs, isolated/junction tables, cardinality)
- **Synthesis**: base_health_report (one-call categorized roll-up of all findings + graph signals; pass include_internal=true for internal-API findings)
- **Visualization**: generate_schema_diagram (Mermaid ER diagram)
- **Live view state** (internal API): get_view (full filter/sort/group/column config), get_view_sections (sidebar groupings)
- **View analysis** (internal API): find_views_using_field (view-side complement of reverse_dependencies), count_records (per-view counts without downloading records), audit_views (hygiene report), find_unused_fields (multi-signal dead-field leads)
- **UI-only surfaces** (internal API): audit_shares (share-link exposure audit), list_interfaces (interface inventory), list_automations (full automation/workflow config dumps)

Tables and fields can be referenced by name (case-insensitive) or Airtable ID.

The live-view-state tools use Airtable's internal (unofficial) API and auto-authenticate
from AIRTABLE_EMAIL/AIRTABLE_PASSWORD in .env. If they fail, they return a structured
error explaining how to fix it; all other tools are unaffected.

LARGE RESULTS ARE SAVED TO DISK. When a tool's result exceeds the inline limit, instead of
the full payload you receive an envelope: {saved_to, bytes, record_count, summary, schema, note}.
`saved_to` is a JSON file under .data/internal_api/; `schema` is a compact shape skeleton of
its structure. Read or jq/grep that file for the detail rather than re-running the tool.
Note: audit_shares writes share-URL tokens to that local file.\
""",
)

# ---------------------------------------------------------------------------
# Public meta-API tools. Logic lives in src/schema_tools.py (shared with the
# `myairtable tools ...` CLI); here we register each as an MCP tool. The
# decorator-free functions keep their names, signatures, and docstrings.
# ---------------------------------------------------------------------------
from src import schema_tools  # noqa: E402

for _public_tool in schema_tools.PUBLIC_TOOLS:
    mcp.tool()(_public_tool)


# ---------------------------------------------------------------------------
# Internal (unofficial) API tools — live view state.
#
# Everything below this line is backed by Airtable's PRIVATE v0.3 web-client
# API (src/internal_api/), NOT the public meta API the tools above use. These
# tools auto-authenticate and return structured errors on failure; they can
# break without notice if Airtable changes the unofficial endpoints.
# ---------------------------------------------------------------------------
from src.internal_api.mcp_tools import register as _register_internal_api_tools  # noqa: E402
from src.internal_api.offload_middleware import ResultOffloadMiddleware, disable_output_schemas  # noqa: E402

_register_internal_api_tools(mcp)

# Offload large results (any tool) to disk; the agent gets a path + schema.
mcp.add_middleware(ResultOffloadMiddleware())
# Tool results are now dynamic (normal shape OR offload envelope), so a fixed
# output schema can't describe them — clear them so strict clients don't reject
# the mismatch. Results flow as JSON text either way.
disable_output_schemas(mcp)


if __name__ == "__main__":
    mcp.run()
