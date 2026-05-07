"""
/api/tools — list all tools, inspect profiles, and invoke tools directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.tools import ALL_TOOLS, get_tools_for_profile, profile_summary

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", summary="List all registered tools")
async def list_tools() -> list[dict[str, Any]]:
    """Return metadata for all registered tools."""
    return [
        {
            "name": t.name,
            "description": (t.description or "").splitlines()[0][:200],
        }
        for t in ALL_TOOLS
    ]


@router.get("/profiles", summary="List all tool profiles and their tool sets")
async def list_profiles() -> dict[str, Any]:
    """
    Return each named tool profile with its tool names and descriptions.

    Profiles:
    - ``default``      — full coding-agent tool set
    - ``web_research`` — web + read-only tools for the frontend agent
    """
    summary = profile_summary()
    result: dict[str, Any] = {}
    tool_desc_map = {t.name: (t.description or "").splitlines()[0][:120] for t in ALL_TOOLS}
    for profile_name, tool_names in summary.items():
        result[profile_name] = {
            "tool_count": len(tool_names),
            "tools": [
                {"name": n, "description": tool_desc_map.get(n, "")}
                for n in tool_names
            ],
        }
    return result


@router.get("/profiles/{profile_name}", summary="Get tools for a specific profile")
async def get_profile(profile_name: str) -> dict[str, Any]:
    """Return the tool list for a named profile."""
    tools = get_tools_for_profile(profile_name)
    return {
        "profile": profile_name,
        "tool_count": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": (t.description or "").splitlines()[0][:200],
            }
            for t in tools
        ],
    }


class ToolInvokeRequest(BaseModel):
    name: str
    args: dict[str, Any] = {}


@router.post("/invoke", summary="Invoke a tool by name")
async def invoke_tool(req: ToolInvokeRequest) -> dict[str, Any]:
    """Invoke a registered tool directly. Returns {result: ...}."""
    tool_map = {t.name: t for t in ALL_TOOLS}
    tool = tool_map.get(req.name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{req.name}' not found")
    try:
        result = tool.invoke(req.args)
        return {"result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
