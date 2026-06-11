"""The CLI --save flag routes results through the shared offload() core."""

import json

from typer.testing import CliRunner

from main import app
from src.internal_api import result_store, tools

runner = CliRunner()


def test_cli_save_offloads_large_result(tmp_path, monkeypatch):
    monkeypatch.setattr(result_store, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("MYAIRTABLE_INLINE_MAX_BYTES", "200")
    big = {"summary": {"n": 100}, "interfaces": [{"i": i} for i in range(100)]}
    monkeypatch.setattr(tools, "list_interfaces", lambda: big)

    result = runner.invoke(app, ["tools", "--save", "list-interfaces"])
    assert result.exit_code == 0
    env = json.loads(result.stdout)
    assert env["saved_to"].endswith("list_interfaces__all.json")
    assert env["summary"] == {"n": 100}
    assert json.loads((tmp_path / "list_interfaces__all.json").read_text()) == big


def test_cli_without_save_returns_inline(tmp_path, monkeypatch):
    monkeypatch.setattr(result_store, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("MYAIRTABLE_INLINE_MAX_BYTES", "200")
    big = {"summary": {"n": 100}, "interfaces": [{"i": i} for i in range(100)]}
    monkeypatch.setattr(tools, "list_interfaces", lambda: big)

    result = runner.invoke(app, ["tools", "list-interfaces"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == big  # full data inline, not offloaded
    assert not list(tmp_path.iterdir())
