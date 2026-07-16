"""Shared scaffolding for the `myairtable tools` CLI group.

The command module (src/myairtable/schema_tools_cli.py) registers its commands onto the
single `tools_app` defined here, so all tools surface under
`myairtable tools <name>`.

Output is JSON on stdout by default (agent-testable, pipeable to jq); --pretty
renders with rich; --save offloads large results to disk (mirroring the MCP
server) and prints the envelope. Failures print a JSON error and exit 1.
"""

import json
import sys
from typing import Annotated, Any

from rich import print as rich_print
from typer import Exit, Option, Typer

from myairtable.result_store import offload

tools_app = Typer(help="Schema introspection & analysis tools — CLI mirrors of the MCP tools.")

_save_state = {"on": False}


@tools_app.callback()
def _tools_callback(
    save: Annotated[bool, Option("--save", help="Offload large results to .data/tools/ and print the envelope (mirrors the MCP server)")] = False,
):
    """Schema introspection & analysis tools."""
    _save_state["on"] = save


def _emit(tool_name: str, result: Any, pretty: bool) -> None:
    if _save_state["on"]:
        result = offload(tool_name, None, result)
    if pretty:
        rich_print(result)
    else:
        print(json.dumps(result, indent=2))


def _fail(error: Exception) -> None:
    print(json.dumps({"error": type(error).__name__, "message": str(error)}, indent=2), file=sys.stderr)
    raise Exit(code=1)
