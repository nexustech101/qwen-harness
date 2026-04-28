"""Project graph context manager.

This package indexes Python source into a compact symbol graph that the agent
can query instead of repeatedly loading broad file context into the model.
"""

from graph.builder import build_project_graph
from graph.context import GraphContextManager
from graph.models import GraphNode, ProjectGraph
from graph.query import ProjectGraphQuery
from graph.store import GraphStore

__all__ = [
    "GraphContextManager",
    "GraphNode",
    "GraphStore",
    "ProjectGraph",
    "ProjectGraphQuery",
    "build_project_graph",
]

