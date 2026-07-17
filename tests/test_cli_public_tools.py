"""The public meta-API tools are mirrored as `myairtable tools <name>` commands.

Registration completeness + adapter behavior (monkeypatched schema_tools, no
network) + error path.
"""

import json

from typer.testing import CliRunner

from myairtable import main, schema_tools  # importing main registers all tools-group commands

runner = CliRunner()

# Every public tool (schema_tools.PUBLIC_TOOLS) must have a kebab-case CLI command.
PUBLIC_COMMANDS = {fn.__name__.replace("_", "-"): fn.__name__ for fn in schema_tools.PUBLIC_TOOLS}


def test_all_public_commands_registered():
    from myairtable.tools_cli import tools_app

    names = {c.name for c in tools_app.registered_commands}
    missing = [k for k in PUBLIC_COMMANDS if k not in names]
    assert not missing, f"public commands missing from the tools group: {missing}"
    # the internal (unofficial) API is gone — no command may depend on it
    assert not ({"get-view", "count-records", "list-automations"} & names)


def test_public_command_emits_json(monkeypatch):
    monkeypatch.setattr(schema_tools, "list_tables", lambda: [{"id": "tblX", "name": "Contacts"}])
    result = runner.invoke(main.app, ["tools", "list-tables"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": "tblX", "name": "Contacts"}]


def test_public_command_save_offloads(monkeypatch, tmp_path):
    from myairtable import result_store

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
