"""
Analysis tools — search in files, count lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from app.core.state import ToolResult
from app.tools.registry import registry
from app.tools.utils import safe_resolve


@registry.tool(
    name="search_in_file",
    category="analysis",
    description="Search for a text pattern or regex in a file, returning matching lines with context",
)
def search_in_file(
    path: Annotated[str, "The path to the file to search"],
    pattern: Annotated[str, "The text pattern or regex to search for"],
    is_regex: Annotated[bool, "Whether the pattern is a regex"] = False,
    max_results: Annotated[int, "The maximum number of results to return"] = 50,
) -> ToolResult:
    try:
        target = safe_resolve(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")
        if not target.is_file():
            return ToolResult(success=False, data="", error=f"Not a file: {path}")

        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        matches: list[str] = []

        if is_regex:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(
                    success=False, data="",
                    error=f"Invalid regex: {e}",
                )
        else:
            compiled = None

        for i, line in enumerate(lines):
            if len(matches) >= max_results:
                break
            if compiled:
                if compiled.search(line):
                    matches.append(f"L{i + 1}: {line}")
            else:
                if pattern.lower() in line.lower():
                    matches.append(f"L{i + 1}: {line}")

        if not matches:
            return ToolResult(
                success=True,
                data=f"No matches for '{pattern}' in {path}",
                metadata={"match_count": 0},
            )

        content = "\n".join(matches)
        return ToolResult(
            success=True,
            data=content,
            metadata={"match_count": len(matches), "capped": len(matches) >= max_results},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Search error: {e}")


@registry.tool(
    name="count_lines",
    category="analysis",
    description="Count lines, characters, and bytes in a file without reading full content",
)
def count_lines(path: Annotated[str, "The path to the file to count lines, characters, and bytes"]) -> ToolResult:
    try:
        target = safe_resolve(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")

        byte_size = target.stat().st_size
        text = target.read_text(encoding="utf-8")
        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        char_count = len(text)

        data = f"{path}: {line_count} lines, {char_count} chars, {byte_size} bytes"
        return ToolResult(
            success=True,
            data=data,
            metadata={
                "lines": line_count,
                "characters": char_count,
                "bytes": byte_size,
            },
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error counting {path}: {e}")
