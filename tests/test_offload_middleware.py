"""End-to-end tests for the offload middleware against a real in-process server."""

import asyncio
import json

import pytest
from fastmcp import Client, FastMCP

from myairtable import result_store
from myairtable.offload_middleware import ResultOffloadMiddleware, disable_output_schemas


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(result_store, "OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("MYAIRTABLE_INLINE_MAX_BYTES", "200")
    return tmp_path


def _server() -> FastMCP:
    mcp = FastMCP("test")

    @mcp.tool()
    def big_dict() -> dict:
        return {"summary": {"n": 100}, "rows": [{"i": i} for i in range(100)]}

    @mcp.tool()
    def big_list() -> list:
        return [{"i": i} for i in range(100)]

    @mcp.tool()
    def small() -> dict:
        return {"ok": True}

    mcp.add_middleware(ResultOffloadMiddleware())
    disable_output_schemas(mcp)
    return mcp


def _call(tool: str) -> str:
    server = _server()  # built outside the loop (the schema sweep uses asyncio.run)

    async def run() -> str:
        async with Client(server) as c:
            r = await c.call_tool(tool, {})
            return r.content[0].text

    return asyncio.run(run())


def test_middleware_offloads_large_dict(tmp_store):
    env = json.loads(_call("big_dict"))
    assert env["saved_to"].endswith("big_dict__all.json")
    assert env["summary"] == {"n": 100}
    assert env["record_count"] == 100
    assert "rows" in env["schema"]
    saved = json.loads((tmp_store / "big_dict__all.json").read_text())
    assert len(saved["rows"]) == 100


def test_middleware_offloads_large_list(tmp_store):
    env = json.loads(_call("big_list"))
    assert env["saved_to"].endswith("big_list__all.json")
    assert env["summary"] == {"count": 100}


def test_middleware_keeps_small_inline(tmp_store):
    d = json.loads(_call("small"))
    assert d == {"ok": True}  # no envelope
    assert not list(tmp_store.iterdir())  # nothing written
