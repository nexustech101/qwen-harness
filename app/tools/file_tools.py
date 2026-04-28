"""
File operation tools — read, write, edit, exists, list.
"""

from __future__ import annotations

import os
import fnmatch

from pathlib import Path
from typing import Annotated, Literal

from app import config
from app.core.state import ToolResult
from app.tools.registry import registry
from app.tools.utils import safe_resolve


# ── Path Security ──────────────────────────────────────────────────────────────

def _validate_path(path: str) -> Path:
    """Resolve a path, confining it to the current working directory."""
    return safe_resolve(path)


# ── Read File ──────────────────────────────────────────────────────────────────

@registry.tool(
    name="read_file",
    category="file",
    description="Read file content with optional line range",
)
def read_file(
    path: Annotated[str, "The path to the file to read"],
    start: Annotated[int | None, "The starting line number (1-based)"] = None,
    end: Annotated[int | None, "The ending line number (1-based, inclusive)"] = None,
) -> ToolResult:
    try:
        target = _validate_path(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")
        if not target.is_file():
            return ToolResult(success=False, data="", error=f"Not a file: {path}")

        # Detect binary
        try:
            raw = target.read_bytes()
            if b"\x00" in raw[:8192]:
                return ToolResult(
                    success=False, data="",
                    error=f"Binary file detected: {path}",
                )
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                success=False, data="",
                error=f"Cannot decode file (not UTF-8): {path}",
            )

        lines = text.splitlines(keepends=True)
        total = len(lines)

        # Handle line range
        start = (start or 1) - 1
        end = end or total
        start = max(0, min(start, total))
        end = max(start, min(end, total))

        # Enforce max read size
        truncated = False
        if end - start > config.MAX_READ_LINES:
            end = start + config.MAX_READ_LINES
            truncated = True

        content = "".join(lines[start:end])

        if len(content.encode("utf-8")) > config.MAX_READ_BYTES:
            content = content[: config.MAX_READ_BYTES]
            truncated = True

        metadata = {
            "total_lines": total,
            "returned_range": f"{start + 1}-{end}",
            "truncated": truncated,
        }

        if truncated:
            content += (
                f"\n\n[TRUNCATED — showing lines {start + 1}-{end} of {total}. "
                f"Use start/end to read more.]"
            )

        return ToolResult(success=True, data=content, metadata=metadata)
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error reading {path}: {e}")


# ── Write File ─────────────────────────────────────────────────────────────────

@registry.tool(
    name="write_file",
    category="file",
    description="Write content to a file (overwrite or append). Creates parent directories.",
)
def write_file(
    path: Annotated[str, "The path to the file to write"],
    content: Annotated[str, "The content to write to the file"],
    mode: Annotated[str, "The write mode: 'overwrite' or 'append'"] = "overwrite",
) -> ToolResult:
    try:
        if not content or not content.strip():
            return ToolResult(
                success=False, data="",
                error="write_file requires non-empty content. Use delete_file to remove a file.",
            )

        target = _validate_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            # Atomic write: temp file + rename
            tmp = target.with_suffix(target.suffix + ".tmp")
            try:
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(target)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise

        byte_count = len(content.encode("utf-8"))
        return ToolResult(
            success=True,
            data=f"Wrote {byte_count} bytes to {path}",
            metadata={"bytes": byte_count, "path": str(target)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error writing {path}: {e}")


# ── Edit File ──────────────────────────────────────────────────────────────────

@registry.tool(
    name="edit_file",
    category="file",
    description="Apply structured edits (replace/insert/delete) to a file",
)
def edit_file(
    path: Annotated[str, "The path to the file to edit"], 
    edits: Annotated[list[dict], "The list of edits to apply"]
) -> ToolResult:
    try:
        target = _validate_path(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")

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
                    return ToolResult(
                        success=False, data="",
                        error="Replace edit requires non-empty 'old_text'",
                    )

                count = content.count(old_text)
                if count == 0:
                    return ToolResult(
                        success=False, data="",
                        error=f"Text not found in {path}: {old_text[:80]}...",
                    )

                if occurrence == 0:
                    # Replace all
                    content = content.replace(old_text, new_text)
                    changes_made.append(f"Replaced all {count} occurrences")
                else:
                    # Replace nth occurrence
                    idx = -1
                    for _ in range(min(occurrence, count)):
                        idx = content.index(old_text, idx + 1)
                    content = (
                        content[:idx] + new_text + content[idx + len(old_text):]
                    )
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
                start = edit.get("start", 1)
                end_val = edit.get("end", start)
                start = max(0, start - 1)
                end = min(end_val, len(lines))
                del lines[start:end]
                content = "".join(lines)
                changes_made.append(f"Deleted lines {start}-{end_val}")

            else:
                return ToolResult(
                    success=False, data="",
                    error=f"Unknown edit type: {edit_type}",
                )

        # Write result atomically
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        summary = "; ".join(changes_made)
        return ToolResult(
            success=True,
            data=f"Edited {path}: {summary}",
            metadata={"changes": changes_made, "path": str(target)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error editing {path}: {e}")


# ── File Exists ────────────────────────────────────────────────────────────────

@registry.tool(
    name="file_exists",
    category="file",
    description="Check if a file exists",
)
def file_exists(path: Annotated[str, "The path to the file to check"]) -> ToolResult:
    try:
        target = _validate_path(path)
        exists = target.exists()
        metadata = {}
        if exists:
            stat = target.stat()
            metadata = {"size": stat.st_size, "modified": stat.st_mtime}
        return ToolResult(
            success=True,
            data="true" if exists else "false",
            metadata=metadata,
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error checking {path}: {e}")


# ── List Directory ─────────────────────────────────────────────────────────────

@registry.tool(
    name="list_directory",
    category="file",
    description="List files in a directory with optional glob filtering",
)
def list_directory(
    path: Annotated[str, "The path to the directory to list"] = ".",
    recursive: Annotated[bool, "Whether to list files recursively"] = False,
    pattern: Annotated[str | None, "Optional glob pattern to filter files"] = None,
) -> ToolResult:
    try:
        target = _validate_path(path)
        if not target.exists():
            return ToolResult(
                success=False, data="",
                error=f"Directory not found: {path}",
            )
        if not target.is_dir():
            return ToolResult(
                success=False, data="",
                error=f"Not a directory: {path}",
            )

        if recursive:
            entries = sorted(str(p.relative_to(target)) for p in target.rglob("*"))
        else:
            entries = sorted(
                f.name + ("/" if f.is_dir() else "") for f in target.iterdir()
            )

        if pattern:
            entries = [e for e in entries if fnmatch.fnmatch(e, pattern)]

        content = "\n".join(entries) if entries else "(empty directory)"
        return ToolResult(
            success=True,
            data=content,
            metadata={"count": len(entries)},
        )
    except Exception as e:
        return ToolResult(
            success=False, data="",
            error=f"Error listing {path}: {e}",
        )
