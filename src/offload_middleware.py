"""FastMCP middleware that offloads large tool results to disk.

A single global hook (`on_call_tool`) covers every registered tool, present and
future, so no per-tool wiring is needed. When a tool's result exceeds the inline
byte limit, the full result is written to disk and the agent receives a small
envelope (path + schema + summary) instead. See src/result_store.py for the
shared offload core.
"""

import asyncio
import json
from typing import Any

from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from .result_store import offload


def _logical_value(result: ToolResult) -> Any:
    """Recover the tool's Python return value from a ToolResult.

    With output schemas disabled (see disable_output_schemas), FastMCP returns
    the value only as JSON text with structured_content=None, so parse the text.
    (When structured_content is present, dict returns sit there directly and
    non-dict returns are wrapped as {"result": <value>}.)
    """
    sc = result.structured_content
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    if sc is not None:
        return sc
    if result.content and isinstance(result.content[0], TextContent):
        text = result.content[0].text
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text  # e.g. a Mermaid diagram string, not JSON
    return None


class ResultOffloadMiddleware(Middleware):
    async def on_call_tool(self, context: Any, call_next: Any) -> ToolResult:
        result = await call_next(context)

        value = _logical_value(result)
        if value is None:
            return result

        tool_name = getattr(context.message, "name", "tool")
        arguments = getattr(context.message, "arguments", None)

        offloaded = offload(tool_name, arguments, value)
        if offloaded is value:
            return result  # stayed inline — pass through untouched

        # Envelope returned as JSON text. Output schemas are disabled server-wide
        # (see disable_output_schemas) so neither this nor the tool's normal
        # return is schema-validated; results flow as JSON text, rogo-mcp style.
        return ToolResult(content=[TextContent(type="text", text=json.dumps(offloaded, indent=2, default=str))])


def disable_output_schemas(mcp: Any) -> None:
    """Clear every registered tool's output schema.

    A tool's result is now dynamic — its normal return shape OR the offload
    envelope — so a fixed output schema can't describe it, and strict MCP
    clients reject the mismatch. Without a schema, results flow as JSON text
    (the rogo-mcp model) and both paths validate cleanly. Idempotent.
    """

    async def _sweep() -> None:
        for tool in await mcp.list_tools():
            if getattr(tool, "output_schema", None):
                tool.output_schema = None

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_sweep())  # no loop (normal startup path)
    else:
        # Already inside a loop — schedule and let the caller's loop drain it.
        asyncio.ensure_future(_sweep())
