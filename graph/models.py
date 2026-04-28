"""Serializable graph model objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ParameterInfo:
    name: str
    kind: str
    annotation: str = ""
    default: str = ""


@dataclass
class ImportInfo:
    module: str
    name: str = ""
    alias: str = ""
    level: int = 0
    line: int = 0
    target: str = ""


@dataclass
class CallSite:
    caller_id: str
    expression: str
    line: int
    col: int = 0
    target_id: str = ""


@dataclass
class SymbolNode:
    id: str
    name: str
    qualname: str
    kind: str
    path: str
    line: int
    end_line: int
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_annotation: str = ""
    decorators: list[str] = field(default_factory=list)
    doc_summary: str = ""
    parent_id: str = ""
    signature: str = ""
    source_file: str = ""
    source_location: str = ""
    file_type: str = "code"
    community: int | None = None


@dataclass
class FileNode:
    path: str
    module: str
    sha1: str
    line_count: int
    imports: list[ImportInfo] = field(default_factory=list)
    syntax_error: str = ""


@dataclass
class GraphNode:
    id: str
    label: str
    file_type: str = "code"
    source_file: str = ""
    source_location: str = ""
    path: str = ""
    line: int = 0
    kind: str = "entity"
    community: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def relation(self) -> str:
        return str(self.metadata.get("relation") or self.kind)

    @property
    def confidence(self) -> str:
        return str(self.metadata.get("confidence") or "EXTRACTED")


@dataclass
class HyperEdge:
    id: str
    nodes: list[str]
    label: str = ""
    relation: str = "group"
    confidence: str = "INFERRED"
    source_file: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectGraph:
    project_root: str
    generated_at: str = field(default_factory=utc_now)
    files: dict[str, FileNode] = field(default_factory=dict)
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    symbols: dict[str, SymbolNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    hyperedges: list[HyperEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectGraph":
        files = {
            path: FileNode(
                **{
                    **file_data,
                    "imports": [ImportInfo(**item) for item in file_data.get("imports", [])],
                }
            )
            for path, file_data in data.get("files", {}).items()
        }
        symbols = {
            sid: SymbolNode(
                **{
                    **symbol_data,
                    "parameters": [
                        ParameterInfo(**item)
                        for item in symbol_data.get("parameters", [])
                    ],
                }
            )
            for sid, symbol_data in data.get("symbols", {}).items()
        }
        nodes = {
            nid: GraphNode(**node_data)
            for nid, node_data in data.get("nodes", {}).items()
        }
        return cls(
            project_root=str(data.get("project_root", "")),
            generated_at=str(data.get("generated_at", "")) or utc_now(),
            files=files,
            nodes=nodes,
            symbols=symbols,
            edges=[GraphEdge(**edge) for edge in data.get("edges", [])],
            calls=[CallSite(**call) for call in data.get("calls", [])],
            hyperedges=[HyperEdge(**item) for item in data.get("hyperedges", [])],
            metadata=dict(data.get("metadata", {})),
        )

