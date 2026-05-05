"""
MCP server instance — import this module to get the shared `mcp` object.

Tools are registered by importing `api.mcp.tools` (side-effect import).
Prompts are registered by importing `api.mcp.prompts` (side-effect import).
Both imports are done in the FastAPI app factory so the MCP instance is fully
populated before any request is served.
"""

from __future__ import annotations

from fastmcp import FastMCP

from api.config.config import get_settings

settings = get_settings()

mcp = FastMCP(settings.mcp_server_name)

__all__ = ["mcp"]
