"""Run MCP server over stdio for Cursor/Grok local integration."""

from app.mcp_server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")