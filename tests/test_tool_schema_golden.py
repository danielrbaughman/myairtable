"""Golden snapshot of the MCP tool schema FastMCP emits for all 28 public tools.

This schema — names, params, types, defaults, required-ness, descriptions — IS the artifact
agents and PyPI consumers bind to. Nothing else in the suite pins it: the tools are
registered by iterating PUBLIC_TOOLS, so a change to any signature or docstring silently
changes the public contract.

It makes a sweeping edit (28 docstrings) reviewable as one diff, and catches the specific
regressions that are invisible in a signature audit: a `base` that became required, a
default that drifted from "" to None (which renders as anyOf:[string,null] and degrades
agent tool-calling), or a tool dropped from the roll-up.

Regenerate after an intentional change:

    uv run python -m tests.test_tool_schema_golden
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "data" / "tool_schema_golden.json"

BASE_DOC = "base: Registered base alias or Airtable base id; empty uses the default base."

REGEN = "uv run python -m tests.test_tool_schema_golden"


def _snapshot() -> dict:
    """The tool schema exactly as an MCP client sees it, normalized for stable diffing."""
    from myairtable.mcp_server import mcp

    async def _collect():
        return await mcp.list_tools()

    tools = [t.to_mcp_tool() for t in asyncio.run(_collect())]
    return {
        "tools": {
            t.name: {
                "description": t.description,
                "parameters": t.inputSchema,
            }
            for t in sorted(tools, key=lambda t: t.name)
        }
    }


def test_tool_schema_matches_golden():
    actual = _snapshot()
    assert GOLDEN.exists(), f"missing golden file; regenerate with: {REGEN}"
    expected = json.loads(GOLDEN.read_text())

    if actual != expected:
        changed = sorted(name for name in set(actual["tools"]) | set(expected["tools"]) if actual["tools"].get(name) != expected["tools"].get(name))
        raise AssertionError("The public MCP tool schema changed for: " + ", ".join(changed) + f"\nIf intentional, regenerate: {REGEN}")


def test_golden_pins_the_multi_base_contract():
    """Guard the properties the golden file exists to protect, in case it is regenerated blind.

    A regenerated snapshot happily records a broken contract; these assertions do not.
    """
    snapshot = _snapshot()
    tools = snapshot["tools"]
    assert len(tools) == 28, f"expected 28 public tools, found {len(tools)}"

    for name, tool in tools.items():
        params = tool["parameters"]
        base = params["properties"].get("base")
        assert base is not None, f"{name}: no base param in the emitted schema"
        assert base == {"type": "string", "default": ""}, f"{name}: base renders as {base}, want a plain optional string"
        assert "base" not in params.get("required", []), f"{name}: base became required"
        assert tool["description"].count(BASE_DOC) == 1, f"{name}: expected exactly one base doc line"


def test_summary_lines_stay_untouched():
    """Tool selection ranks primarily on the summary line; the base plumbing must not touch it."""
    for name, tool in _snapshot()["tools"].items():
        summary = tool["description"].split("\n", 1)[0]
        assert "Registered base alias" not in summary, f"{name}: base doc leaked into the summary line"
        assert summary.strip(), f"{name}: empty summary line"
        # The base doc belongs under Args:, which never appears on line one.
        assert not summary.startswith("Args:"), f"{name}: summary line is missing"


def _regenerate() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(_snapshot(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    _regenerate()
