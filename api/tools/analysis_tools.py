"""
Analysis tools — search in files, count lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.tools.utils import safe_resolve


@tool
def search_in_file(
    path: Annotated[str, "Path to the file to search"],
    pattern: Annotated[str, "Text pattern or regex to search for"],
    is_regex: Annotated[bool, "Whether the pattern is a regex"] = False,
    max_results: Annotated[int, "Maximum number of results to return"] = 50,
) -> str:
    """Search for a text pattern or regex in a file, returning matching lines."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        if not target.is_file():
            return f"ERROR: Not a file: {path}"
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        matches: list[str] = []
        if is_regex:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                return f"ERROR: Invalid regex: {exc}"
        else:
            compiled = None
        for i, line in enumerate(lines):
            if len(matches) >= max_results:
                break
            if compiled:
                if compiled.search(line):
                    matches.append(f"L{i + 1}: {line}")
            elif pattern.lower() in line.lower():
                matches.append(f"L{i + 1}: {line}")
        if not matches:
            return f"No matches for '{pattern}' in {path}"
        return "\n".join(matches)
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def count_lines(path: Annotated[str, "Path to the file"]) -> str:
    """Count lines, characters, and bytes in a file."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        byte_size = target.stat().st_size
        text = target.read_text(encoding="utf-8")
        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        char_count = len(text)
        return f"{path}: {line_count} lines, {char_count} chars, {byte_size} bytes"
    except Exception as exc:
        return f"ERROR: {exc}"