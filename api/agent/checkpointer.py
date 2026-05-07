"""
AsyncSqliteSaver checkpointer wrapper for LangGraph.

Provides get_checkpointer() which returns a ready-to-use
AsyncSqliteSaver connected to the configured DB path.
"""

from __future__ import annotations

from pathlib import Path

from api.config.config import get_settings

settings = get_settings()


def get_checkpointer_path() -> Path:
    """Return the SQLite path used for LangGraph checkpoints."""
    db_path = Path(getattr(settings, "database_path", "agent.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def make_checkpointer():
    """Create and return an AsyncSqliteSaver instance.

    Usage::

        async with make_checkpointer() as checkpointer:
            graph = get_compiled_graph(checkpointer=checkpointer)
            result = await graph.ainvoke(state, config)
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path = get_checkpointer_path()
    return AsyncSqliteSaver.from_conn_string(str(path))
