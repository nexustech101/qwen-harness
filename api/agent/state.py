"""
AgentState — the LangGraph state schema shared across all graph nodes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State threaded through the LangGraph agent graph."""

    # Message history — langgraph manages appending via add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Session / routing metadata
    session_id: str
    provider: Literal["ollama", "openai", "anthropic"]
    model: str

    # Tool profile — controls which tool set the LLM has access to.
    # "default" = full coding-agent tools; "web_research" = web + read-only only.
    tool_profile: str

    # Turn budget — incremented each time the model responds
    tool_calls_made: int
    max_turns: int

    # Lifecycle flag set by graph nodes
    status: Literal["running", "done", "error"]
