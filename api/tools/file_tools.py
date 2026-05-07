"""
File operation tools — read, write, edit, exists, list.
"""

from __future__ import annotations

import fnmatch

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.tools.utils import safe_resolve

MAX_READ_LINES = 2000
MAX_READ_BYTES = 500_000


def _validate_path(path: str) -> Path:
    return safe_resolve(path)


@tool
def read_file(
    path: Annotated[str, "Path to the file to read"],
    start: Annotated[int | None, "Starting line number (1-based)"] = None,
    end: Annotated[int | None, "Ending line number (1-based, inclusive)"] = None,
) -> str:
    """Read file content with optional line range."""
    try:
        target = _validate_path(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        if not target.is_file():
            return f"ERROR: Not a file: {path}"
        try:
            raw = target.read_bytes()
            if b"\x00" in raw[:8192]:
                return f"ERROR: Binary file detected: {path}"
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return f"ERROR: Cannot decode file (not UTF-8): {path}"

        lines = text.splitlines(keepends=True)
        total = len(lines)
        s = (start or 1) - 1
        e = end or total
        s = max(0, min(s, total))
        e = max(s, min(e, total))
        truncated = False
        if e - s > MAX_READ_LINES:
            e = s + MAX_READ_LINES
            truncated = True
        content = "".join(lines[s:e])
        if len(content.encode("utf-8")) > MAX_READ_BYTES:
            content = content[:MAX_READ_BYTES]
            truncated = True
        if truncated:
            content += f"\n\n[TRUNCATED — showing lines {s + 1}-{e} of {total}. Use start/end for more.]"
        return content
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR reading {path}: {exc}"


@tool
def write_file(
    path: Annotated[str, "Path to the file to write"],
    content: Annotated[str, "Content to write"],
    mode: Annotated[str, "Write mode: 'overwrite' or 'append'"] = "overwrite",
) -> str:
    """Write content to a file (overwrite or append). Creates parent directories."""
    try:
        if not content or not content.strip():
            return "ERROR: write_file requires non-empty content."
        target = _validate_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            tmp = target.with_suffix(target.suffix + ".tmp")
            try:
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(target)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
        return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR writing {path}: {exc}"


@tool
def edit_file(
    path: Annotated[str, "Path to the file to edit"],
    edits: Annotated[list[dict], "List of edit operations (type, old_text, new_text, ...)"],
) -> str:
    """Apply structured edits (replace/insert/delete) to a file."""
    try:
        target = _validate_path(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        content = target.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        changes_made: list[str] = []
        for edit in edits:
            edit_type = edit.get("type", "")
            if edit_type == "replace":
                old_text = edit.get("old_text", "")
                new_text = edit.get("new_text", "")
                occurrence = edit.get("occurrence", 1)
                if not old_text:
                    return "ERROR: Replace edit requires non-empty 'old_text'"
                count = content.count(old_text)
                if count == 0:
                    return f"ERROR: Text not found in {path}: {old_text[:80]}"
                if occurrence == 0:
                    content = content.replace(old_text, new_text)
                    changes_made.append(f"Replaced all {count} occurrences")
                else:
                    idx = -1
                    for _ in range(min(occurrence, count)):
                        idx = content.index(old_text, idx + 1)
                    content = content[:idx] + new_text + content[idx + len(old_text):]
                    changes_made.append(f"Replaced occurrence {occurrence}")
                lines = content.splitlines(keepends=True)
            elif edit_type == "insert":
                line = edit.get("line", 1)
                position = edit.get("position", "before")
                text = edit.get("text", edit.get("new_text", ""))
                if not text.endswith("\n"):
                    text += "\n"
                idx = max(0, min(line - 1, len(lines)))
                if position == "after":
                    idx = min(idx + 1, len(lines))
                lines.insert(idx, text)
                content = "".join(lines)
                changes_made.append(f"Inserted at line {line} ({position})")
            elif edit_type == "delete":
                s = edit.get("start", 1)
                ev = edit.get("end", s)
                si = max(0, s - 1)
                ei = min(ev, len(lines))
                del lines[si:ei]
                content = "".join(lines)
                changes_made.append(f"Deleted lines {s}-{ev}")
            else:
                return f"ERROR: Unknown edit type: {edit_type}"
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return f"Edited {path}: {'; '.join(changes_made)}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR editing {path}: {exc}"


@tool
def file_exists(path: Annotated[str, "Path to check"]) -> str:
    """Check if a file or directory exists at the given path."""
    try:
        target = _validate_path(path)
        return "true" if target.exists() else "false"
    except Exception as exc:
        return f"ERROR checking {path}: {exc}"


@tool
def list_directory(
    path: Annotated[str, "Directory path to list"] = ".",
    recursive: Annotated[bool, "List files recursively"] = False,
    pattern: Annotated[str | None, "Glob pattern to filter results"] = None,
) -> str:
    """List files in a directory with optional glob filtering."""
    try:
        target = _validate_path(path)
        if not target.exists():
            return f"ERROR: Directory not found: {path}"
        if not target.is_dir():
            return f"ERROR: Not a directory: {path}"
        if recursive:
            entries = sorted(str(p.relative_to(target)) for p in target.rglob("*"))
        else:
            entries = sorted(f.name + ("/" if f.is_dir() else "") for f in target.iterdir())
        if pattern:
            entries = [e for e in entries if fnmatch.fnmatch(e, pattern)]
        return "\n".join(entries) if entries else "(empty directory)"
    except Exception as exc:
        return f"ERROR listing {path}: {exc}"