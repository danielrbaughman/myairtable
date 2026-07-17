"""Golden snapshot of the public tool contract for all 28 tools.

The 28 functions in PUBLIC_TOOLS are the artifact PyPI consumers bind to, and
that rogo-mcp registers as MCP tools (via functools.wraps, so their signatures
and docstrings become the tool schema and description agents read). Nothing else
in the suite pins the whole surface at once: the tools are consumed by iterating
PUBLIC_TOOLS, so a change to any signature or docstring silently changes the
public contract.

This snapshots each tool's name, parameters (kind/default/annotation), and
docstring. It makes a sweeping edit (e.g. 28 docstrings) reviewable as one diff
and catches the regressions a spot check misses: a `base` that became required
or positional, a default that drifted from "" to None, a param renamed, or a
docstring mangled.

The snapshot is derived by introspection, not FastMCP — myairtable no longer
ships an MCP server (the tools moved to rogo-mcp), but the contract is exactly
the function signature + docstring.

Regenerate after an intentional change:

    uv run python -m tests.test_tool_schema_golden
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from myairtable import schema_tools

GOLDEN = Path(__file__).parent / "data" / "tool_schema_golden.json"

BASE_DOC = "base: Registered base alias or Airtable base id; empty uses the default base."

REGEN = "uv run python -m tests.test_tool_schema_golden"


def _snapshot() -> dict:
    """Each public tool's name, parameters, and docstring — the bound contract."""
    tools = {}
    for fn in schema_tools.PUBLIC_TOOLS:
        sig = inspect.signature(fn)
        params = {
            name: {
                "kind": p.kind.name,
                "default": None if p.default is inspect.Parameter.empty else repr(p.default),
                # schema_tools uses `from __future__ import annotations`, so these
                # are already strings (e.g. "str", 'Literal["typescript", ...]').
                "annotation": None if p.annotation is inspect.Parameter.empty else str(p.annotation),
            }
            for name, p in sig.parameters.items()
        }
        tools[fn.__name__] = {"doc": inspect.getdoc(fn), "params": params}
    return {"tools": dict(sorted(tools.items()))}


def test_tool_contract_matches_golden():
    actual = _snapshot()
    assert GOLDEN.exists(), f"missing golden file; regenerate with: {REGEN}"
    expected = json.loads(GOLDEN.read_text())

    if actual != expected:
        changed = sorted(name for name in set(actual["tools"]) | set(expected["tools"]) if actual["tools"].get(name) != expected["tools"].get(name))
        raise AssertionError("The public tool contract changed for: " + ", ".join(changed) + f"\nIf intentional, regenerate: {REGEN}")


def test_golden_pins_the_multi_base_contract():
    """Guard the properties the golden file exists to protect, in case it is regenerated blind.

    A regenerated snapshot happily records a broken contract; these assertions do not.
    """
    tools = _snapshot()["tools"]
    assert len(tools) == 28, f"expected 28 public tools, found {len(tools)}"

    for name, tool in tools.items():
        base = tool["params"].get("base")
        assert base is not None, f"{name}: no base param"
        assert base["kind"] == "KEYWORD_ONLY", f"{name}: base is {base['kind']}, not keyword-only"
        assert base["default"] == "''", f"{name}: base default is {base['default']}, want an empty string"
        assert base["annotation"] == "str", f"{name}: base annotation is {base['annotation']}, want str"
        assert (tool["doc"] or "").count(BASE_DOC) == 1, f"{name}: expected exactly one base doc line"


def test_summary_lines_stay_untouched():
    """Tool selection ranks primarily on the summary line; the base plumbing must not touch it."""
    for name, tool in _snapshot()["tools"].items():
        summary = (tool["doc"] or "").split("\n", 1)[0]
        assert "Registered base alias" not in summary, f"{name}: base doc leaked into the summary line"
        assert summary.strip(), f"{name}: empty summary line"
        assert not summary.startswith("Args:"), f"{name}: summary line is missing"


def _regenerate() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(_snapshot(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    _regenerate()
