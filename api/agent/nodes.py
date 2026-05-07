"""
LangGraph node functions for the agent graph.

Nodes:
  call_model   — invoke the LLM with current messages, streaming deltas as SSE events
  route_after_model — conditional edge deciding whether to call tools or finish
"""

from __future__ import annotations

import json as _json
import uuid as _uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode

from api.agent.state import AgentState
from api.config.config import get_settings
from api.llm.factory import create_llm
from api.tools import ALL_TOOLS, get_tools_for_profile

settings = get_settings()


def _get_llm_with_tools(provider: str, model: str, tool_profile: str = "default"):
    """Return an LLM bound to the tools for *tool_profile*."""
    llm = create_llm(provider, model, streaming=True)
    tools = get_tools_for_profile(tool_profile)
    return llm.bind_tools(tools)


async def call_model(state: AgentState) -> dict[str, Any]:
    """LangGraph node: invoke the LLM and return the AI message."""
    provider = state["provider"]
    model = state["model"]
    tool_profile = state.get("tool_profile", "default")

    llm = _get_llm_with_tools(provider, model, tool_profile)
    response: AIMessage = await llm.ainvoke(state["messages"])

    # Some models (e.g. qwen2.5-coder via Ollama) output tool calls as JSON text
    # instead of structured tool_calls. Detect and convert so ToolNode can handle them.
    if not response.tool_calls and isinstance(response.content, str):
        content = response.content.strip()
        if content.startswith("{"):
            try:
                parsed = _json.loads(content)
                tool_name = parsed.get("name") or parsed.get("tool")
                tool_args = parsed.get("arguments") or parsed.get("args") or {}
                if tool_name and isinstance(tool_args, dict):
                    response = AIMessage(
                        content="",
                        tool_calls=[{
                            "id": f"call_{_uuid.uuid4().hex[:8]}",
                            "name": tool_name,
                            "args": tool_args,
                            "type": "tool_call",
                        }],
                    )
            except (_json.JSONDecodeError, AttributeError):
                pass

    return {
        "messages": [response],
        "tool_calls_made": state["tool_calls_made"] + 1,
    }


def route_after_model(state: AgentState) -> str:
    """Conditional edge: route to tool execution or END."""
    last: BaseMessage = state["messages"][-1]

    # If the LLM requested tool calls and we haven't hit the turn budget
    if (
        isinstance(last, AIMessage)
        and last.tool_calls
        and state["tool_calls_made"] < state["max_turns"]
    ):
        return "tools"

    return "__end__"


# ToolNode is seeded with ALL tools (the full union across all profiles).
# The LLM is bound with only the profile's subset — so it will never *call*
# tools outside its profile — but having the full set here means ToolNode can
# always execute whatever the LLM requests without a key-not-found error.
tool_node = ToolNode(ALL_TOOLS)
