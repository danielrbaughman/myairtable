from fastmcp import FastMCP

mcp = FastMCP("myairtable")


@mcp.tool()
def hello() -> str:
    """Say hello from the myairtable MCP server."""
    return "Hello from myairtable!"


if __name__ == "__main__":
    mcp.run()
