"""CLI adapters for the public meta-API tools.

Thin mirrors of the public MCP tools — all logic lives in src/myairtable/schema_tools.py
(the same functions the MCP server registers, so a CLI invocation verifies MCP
behavior). Commands register onto the shared `tools_app` (src/myairtable/tools_cli.py), so
everything is `myairtable tools <name>`.

Public tools raise ValueError on bad input; commands convert that to a JSON
error + exit 1 via _fail.
"""

from typing import Annotated

from typer import Argument, Option

from myairtable import schema_tools
from myairtable.tools_cli import _emit, _fail, tools_app

_PRETTY = Option("--pretty", help="Rich output instead of plain JSON")


# --- no-argument tools ------------------------------------------------------


@tools_app.command("get-schema")
def get_schema_command(pretty: Annotated[bool, _PRETTY] = False):
    """Full base schema: all tables with their fields and views."""
    try:
        _emit("get_schema", schema_tools.get_schema(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("list-tables")
def list_tables_command(pretty: Annotated[bool, _PRETTY] = False):
    """List all tables with name, field count, and primary field."""
    try:
        _emit("list_tables", schema_tools.list_tables(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("get-links")
def get_links_command(pretty: Annotated[bool, _PRETTY] = False):
    """All link fields between tables, including their inverse fields."""
    try:
        _emit("get_links", schema_tools.get_links(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("check-link-symmetry")
def check_link_symmetry_command(pretty: Annotated[bool, _PRETTY] = False):
    """Check link fields for missing inverses or broken inverse references."""
    try:
        _emit("check_link_symmetry", schema_tools.check_link_symmetry(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("find-invalid-fields")
def find_invalid_fields_command(pretty: Annotated[bool, _PRETTY] = False):
    """Fields marked invalid by Airtable or with broken references."""
    try:
        _emit("find_invalid_fields", schema_tools.find_invalid_fields(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("find-circular-references")
def find_circular_references_command(pretty: Annotated[bool, _PRETTY] = False):
    """Detect circular references in formula fields and link chains."""
    try:
        _emit("find_circular_references", schema_tools.find_circular_references(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("generate-schema-diagram")
def generate_schema_diagram_command(pretty: Annotated[bool, _PRETTY] = False):
    """Mermaid ER diagram of all tables and their link relationships."""
    try:
        _emit("generate_schema_diagram", schema_tools.generate_schema_diagram(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("base-stats")
def base_stats_command(pretty: Annotated[bool, _PRETTY] = False):
    """Aggregate base statistics: table/field counts, most connected tables."""
    try:
        _emit("base_stats", schema_tools.base_stats(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("find-dead-fields")
def find_dead_fields_command(pretty: Annotated[bool, _PRETTY] = False):
    """Fields not referenced by any formula, lookup, or rollup."""
    try:
        _emit("find_dead_fields", schema_tools.find_dead_fields(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("analyze-type-consistency")
def analyze_type_consistency_command(pretty: Annotated[bool, _PRETTY] = False):
    """Calculated fields whose result type may not match expectations."""
    try:
        _emit("analyze_type_consistency", schema_tools.analyze_type_consistency(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("find-type-ambiguities")
def find_type_ambiguities_command(pretty: Annotated[bool, _PRETTY] = False):
    """Computed fields with ambiguous or unknown result types."""
    try:
        _emit("find_type_ambiguities", schema_tools.find_type_ambiguities(), pretty)
    except Exception as e:
        _fail(e)


# --- table-required ---------------------------------------------------------


@tools_app.command("describe-table")
def describe_table_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Describe a table: all fields with types, descriptions, and options."""
    try:
        _emit("describe_table", schema_tools.describe_table(table), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("get-lookups-and-rollups")
def get_lookups_and_rollups_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Lookup and rollup fields for a table, showing what they derive from."""
    try:
        _emit("get_lookups_and_rollups", schema_tools.get_lookups_and_rollups(table), pretty)
    except Exception as e:
        _fail(e)


# --- table-optional ---------------------------------------------------------


@tools_app.command("list-formula-fields")
def list_formula_fields_command(
    table: Annotated[str, Argument(help="Optional table name or ID; all tables if omitted")] = "",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """All formula fields with their expressions and result types."""
    try:
        _emit("list_formula_fields", schema_tools.list_formula_fields(table), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("analyze-formula-complexity")
def analyze_formula_complexity_command(
    table: Annotated[str, Argument(help="Optional table name or ID; all tables if omitted")] = "",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Formula complexity: nesting depth, function usage, field-ref counts."""
    try:
        _emit("analyze_formula_complexity", schema_tools.analyze_formula_complexity(table), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("get-select-options")
def get_select_options_command(
    table: Annotated[str, Argument(help="Optional table name or ID; all tables if omitted")] = "",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """All select field options across tables; finds duplicates."""
    try:
        _emit("get_select_options", schema_tools.get_select_options(table), pretty)
    except Exception as e:
        _fail(e)


# --- table + field ----------------------------------------------------------


@tools_app.command("describe-field")
def describe_field_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Deep dive on a field: type, options, linked table, formula, dependencies."""
    try:
        _emit("describe_field", schema_tools.describe_field(table, field), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("trace-field-dependencies")
def trace_field_dependencies_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Walk the full dependency chain for a field (formulas, lookups, rollups)."""
    try:
        _emit("trace_field_dependencies", schema_tools.trace_field_dependencies(table, field), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("flatten-formula")
def flatten_formula_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Expand nested formula references inline (fully resolved expression)."""
    try:
        _emit("flatten_formula", schema_tools.flatten_formula(table, field), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("reverse-dependencies")
def reverse_dependencies_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Find all fields that depend on a field (what breaks if it changes)."""
    try:
        _emit("reverse_dependencies", schema_tools.reverse_dependencies(table, field), pretty)
    except Exception as e:
        _fail(e)


# --- special signatures -----------------------------------------------------


@tools_app.command("search-fields")
def search_fields_command(
    query: Annotated[str, Option("--query", "-q", help="Substring to match against field names")] = "",
    field_type: Annotated[str, Option("--field-type", "-t", help="Exact field type to match")] = "",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Search fields by name or type across all tables."""
    try:
        _emit("search_fields", schema_tools.search_fields(query, field_type), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("get-formula")
def get_formula_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    flatten: Annotated[bool, Option("--flatten", help="Inline nested formula references")] = False,
    pretty: Annotated[bool, _PRETTY] = False,
):
    """A formula field's expression with human-readable field names."""
    try:
        _emit("get_formula", schema_tools.get_formula(table, field, flatten), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("transpile")
def transpile_command(
    table: Annotated[str, Argument(help="Table name or ID")],
    field: Annotated[str, Argument(help="Field name or ID")],
    language: Annotated[str, Option("--language", "-l", help="Target: typescript, javascript, or python")] = "typescript",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Convert an Airtable formula to Python, TypeScript, or JavaScript."""
    try:
        _emit("transpile", schema_tools.transpile(table, field, language), pretty)  # ty: ignore[invalid-argument-type]
    except Exception as e:
        _fail(e)


@tools_app.command("dependency-graph-metrics")
def dependency_graph_metrics_command(
    table: Annotated[str, Argument(help="Optional table name or ID to scope the field list")] = "",
    top_n: Annotated[int, Option("--top-n", help="Entries per ranking")] = 20,
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Field blast radius, dependency depth, and centrality across the base."""
    try:
        _emit("dependency_graph_metrics", schema_tools.dependency_graph_metrics(table, top_n), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("table-connectivity")
def table_connectivity_command(pretty: Annotated[bool, _PRETTY] = False):
    """Table link graph: hubs, isolated tables, junctions, and relationship cardinality."""
    try:
        _emit("table_connectivity", schema_tools.table_connectivity(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("formula-function-usage")
def formula_function_usage_command(
    table: Annotated[str, Argument(help="Optional table name or ID; all tables if omitted")] = "",
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Base-wide histogram of which functions formulas use, and where."""
    try:
        _emit("formula_function_usage", schema_tools.formula_function_usage(table), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("base-health-report")
def base_health_report_command(pretty: Annotated[bool, _PRETTY] = False):
    """One-call categorized roll-up of everything notable about the base."""
    try:
        _emit("base_health_report", schema_tools.base_health_report(), pretty)
    except Exception as e:
        _fail(e)


@tools_app.command("compare-tables")
def compare_tables_command(
    table_a: Annotated[str, Argument(help="First table name or ID")],
    table_b: Annotated[str, Argument(help="Second table name or ID")],
    pretty: Annotated[bool, _PRETTY] = False,
):
    """Compare field structures between two tables (shared and unique fields)."""
    try:
        _emit("compare_tables", schema_tools.compare_tables(table_a, table_b), pretty)
    except Exception as e:
        _fail(e)
