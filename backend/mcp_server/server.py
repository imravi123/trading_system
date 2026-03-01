"""MCP Server — exposes trading tools via stdio transport for Claude Desktop / Claude Code.

Run standalone:
  python -m backend.mcp_server.server

Or via uvicorn (SSE transport) — add to main.py when needed.
"""
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from backend.mcp_server.tools import TOOLS, call_tool

app = Server("trading-system")


# ── Resources ─────────────────────────────────────────────────────────────────
@app.list_resources()
async def list_resources():
    """No resources defined yet."""
    return []


# ── Tools ─────────────────────────────────────────────────────────────────────
@app.list_tools()
async def list_tools():
    """Return all registered trading tools."""
    return TOOLS


@app.call_tool()
async def _call_tool(name: str, arguments: dict):
    result = await call_tool(name, arguments)
    return [TextContent(type="text", text=result)]


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
