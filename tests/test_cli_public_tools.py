"""The public meta-API tools are mirrored as `myairtable tools <name>` commands.

Registration completeness + adapter behavior (monkeypatched schema_tools, no
network) + error path + MCP parity.
"""

import asyncio
import json

from typer.testing import CliRunner

import main  # import registers all tools-group commands
from src import schema_tools

runner = CliRunner()

# kebab name -> snake function name (all 24 public tools)
PUBLIC_COMMANDS = {
    "get-schema": "get_schema",
    "list-tables": "list_tables",
    "describe-table": "describe_table",
    "describe-field": "describe_field",
    "search-fields": "search_fields",
    "get-links": "get_links",
    "get-lookups-and-rollups": "get_lookups_and_rollups",
    "trace-field-dependencies": "trace_field_dependencies",
    "get-formula": "get_formula",
    "list-formula-fields": "list_formula_fields",
    "flatten-formula": "flatten_formula",
    "check-link-symmetry": "check_link_symmetry",
    "find-invalid-fields": "find_invalid_fields",
    "analyze-formula-complexity": "analyze_formula_complexity",
    "transpile": "transpile",
    "reverse-dependencies": "reverse_dependencies",
    "find-circular-references": "find_circular_references",
    "generate-schema-diagram": "generate_schema_diagram",
    "base-stats": "base_stats",
    "find-dead-fields": "find_dead_fields",
    "compare-tables": "compare_tables",
    "get-select-options": "get_select_options",
    "analyze-type-consistency": "analyze_type_consistency",
    "find-type-ambiguities": "find_type_ambiguities",
}


def test_all_public_commands_registered():
    from src.tools_cli import tools_app

    names = {c.name for c in tools_app.registered_commands}
    missing = [k for k in PUBLIC_COMMANDS if k not in names]
    assert not missing, f"public commands missing from the tools group: {missing}"
    # internal commands still present too
    assert {"get-view", "count-records", "list-automations"} <= names


def test_public_command_emits_json(monkeypatch):
    monkeypatch.setattr(schema_tools, "list_tables", lambda: [{"id": "tblX", "name": "Contacts"}])
    result = runner.invoke(main.app, ["tools", "list-tables"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": "tblX", "name": "Contacts"}]


def test_public_command_save_offloads(monkeypatch, tmp_path):
    from src.internal_api import result_store

    monkeypatch.setattr(result_store, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("MYAIRTABLE_INLINE_MAX_BYTES", "200")
    big = {"base_id": "appX", "tables": [{"id": f"tbl{i}"} for i in range(100)]}
    monkeypatch.setattr(schema_tools, "get_schema", lambda: big)

    result = runner.invoke(main.app, ["tools", "--save", "get-schema"])
    assert result.exit_code == 0
    env = json.loads(result.stdout)
    assert env["saved_to"].endswith("get_schema__all.json")
    assert json.loads((tmp_path / "get_schema__all.json").read_text()) == big


def test_public_command_error_path(monkeypatch):
    def boom(_table):
        raise ValueError("Table not found: Nope")

    monkeypatch.setattr(schema_tools, "describe_table", boom)
    result = runner.invoke(main.app, ["tools", "describe-table", "Nope"])
    assert result.exit_code == 1
    assert "Table not found" in result.stderr


def test_mcp_still_exposes_all_tools():
    import mcp_server

    async def names():
        return sorted(t.name for t in await mcp_server.mcp.list_tools())

    all_names = asyncio.run(names())
    assert len(all_names) == 33
    assert {fn for fn in PUBLIC_COMMANDS.values()} <= set(all_names)
    assert {"get_view", "list_automations"} <= set(all_names)
