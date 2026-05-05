"""
Workspace-wide tools — search across project, file management ops.

These tools give agents the ability to navigate and manage the full project,
not just individual files.
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil

from pathlib import Path
from typing import Annotated, Literal

from app import config
from app.core.state import ToolResult
from api.tools.registry import registry
from api.tools.utils import safe_resolve

# Directories to always skip during workspace searches
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", "*.egg-info", Path(config.WORKSPACE_HOME).name,
}

# Binary/non-searchable extensions
_BINARY_EXTS = {
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".sqlite", ".db",
}


def _should_skip_dir(name: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    return name in _SKIP_DIRS or name.startswith(".")


def _is_text_file(path: Path) -> bool:
    """Quick check if a file is likely a text file."""
    return path.suffix.lower() not in _BINARY_EXTS


def _walk_files(
    root: Path,
    include: str | None = None,
    exclude: str | None = None,
) -> list[Path]:
    """Walk workspace files, respecting skip dirs and filters."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(root))

            if (include and not fnmatch.fnmatch(rel, include)
                    and not fnmatch.fnmatch(fname, include)
                    or exclude and (fnmatch.fnmatch(rel, exclude)
                    or fnmatch.fnmatch(fname, exclude))):
                continue
            
            # if exclude and (fnmatch.fnmatch(rel, exclude) or fnmatch.fnmatch(fname, exclude)):
            #     continue

            files.append(fpath)

    return files


# ── Grep Workspace ─────────────────────────────────────────────────────────────

@registry.tool(
    name="grep_workspace",
    category="workspace",
    description="Search for a text pattern across all project files (like ripgrep). Returns file:line:match.",
    idempotent=True,
)
def grep_workspace(
    pattern: Annotated[str, "The text pattern to search for"],
    is_regex: Annotated[bool, "Whether the pattern is a regular expression"] = False,
    include: Annotated[str | None, "Glob pattern to include"] = None,
    exclude: Annotated[str | None, "Glob pattern to exclude"] = None,
    max_results: Annotated[int, "Maximum number of results to return"] = 100,
) -> ToolResult:
    try:
        root = Path.cwd().resolve()
        files = _walk_files(root, include, exclude)

        if is_regex:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(success=False, data="", error=f"Invalid regex: {e}")
        else:
            compiled = None

        matches: list[str] = []
        files_searched = 0

        for fpath in sorted(files):
            if not _is_text_file(fpath):
                continue

            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue

            files_searched += 1

            for i, line in enumerate(text.splitlines(), 1):
                if len(matches) >= max_results:
                    break

                hit = (
                    compiled.search(line) if compiled
                    else pattern.lower() in line.lower()
                )
                if hit:
                    rel = fpath.relative_to(root)
                    matches.append(f"{rel}:{i}: {line.rstrip()}")

            if len(matches) >= max_results:
                break

        if not matches:
            return ToolResult(
                success=True,
                data=f"No matches for '{pattern}' across {files_searched} files",
                metadata={"match_count": 0, "files_searched": files_searched},
            )

        content = "\n".join(matches)
        capped = len(matches) >= max_results
        if capped:
            content += f"\n\n[CAPPED at {max_results} results — use include/exclude to narrow]"

        return ToolResult(
            success=True,
            data=content,
            metadata={
                "match_count": len(matches),
                "files_searched": files_searched,
                "capped": capped,
            },
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Grep error: {e}")


# ── Find Files ─────────────────────────────────────────────────────────────────

@registry.tool(
    name="find_files",
    category="workspace",
    description="Find files by name or glob pattern across the workspace",
    idempotent=True,
)
def find_files(
    pattern: Annotated[str, "The filename or glob pattern to search for"],
    path: Annotated[str, "The directory path to search in"] = ".",
    max_results: Annotated[int, "Maximum number of results to return"] = 50,
) -> ToolResult:
    try:
        root = safe_resolve(path)
        if not root.exists():
            return ToolResult(success=False, data="", error=f"Directory not found: {path}")

        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            for fname in filenames:
                if len(results) >= max_results:
                    break

                # Match against filename or relative path
                fpath = Path(dirpath) / fname
                rel = str(fpath.relative_to(root))

                if (fnmatch.fnmatch(fname, pattern)
                        or fnmatch.fnmatch(rel, pattern)
                        or pattern.lower() in fname.lower()):
                    results.append(rel)

            if len(results) >= max_results:
                break

        if not results:
            return ToolResult(
                success=True,
                data=f"No files matching '{pattern}'",
                metadata={"count": 0},
            )

        content = "\n".join(sorted(results))
        return ToolResult(
            success=True,
            data=content,
            metadata={"count": len(results), "capped": len(results) >= max_results},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Find error: {e}")


# ── Create Directory ───────────────────────────────────────────────────────────

@registry.tool(
    name="create_directory",
    category="workspace",
    description="Create a directory (and parent directories)",
)
def create_directory(path: Annotated[str, "The directory path to create"]) -> ToolResult:
    try:
        target = safe_resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return ToolResult(
            success=True,
            data=f"Created directory: {path}",
            metadata={"path": str(target)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Error creating directory: {e}")


# ── Move / Rename File ────────────────────────────────────────────────────────

@registry.tool(
    name="move_file",
    category="workspace",
    description="Move or rename a file or directory",
)
def move_file(
    source: Annotated[str, "The source file or directory to move"],
    destination: Annotated[str, "The destination path"],
) -> ToolResult:
    try:
        src = safe_resolve(source)
        dst = safe_resolve(destination)

        if not src.exists():
            return ToolResult(success=False, data="", error=f"Source not found: {source}")

        if dst.exists():
            return ToolResult(success=False, data="", error=f"Destination already exists: {destination}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        return ToolResult(
            success=True,
            data=f"Moved {source} → {destination}",
            metadata={"source": str(src), "destination": str(dst)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Move error: {e}")


# ── Delete File ────────────────────────────────────────────────────────────────

@registry.tool(
    name="delete_file",
    category="workspace",
    description="Delete a file or empty directory",
)
def delete_file(path: str) -> ToolResult:
    try:
        target = safe_resolve(path)

        if not target.exists():
            return ToolResult(success=False, data="", error=f"Not found: {path}")

        if target.is_file():
            target.unlink()
            return ToolResult(success=True, data=f"Deleted file: {path}")
        elif target.is_dir():
            # Only delete empty directories for safety
            children = list(target.iterdir())
            if children:
                return ToolResult(
                    success=False, data="",
                    error=f"Directory not empty ({len(children)} items): {path}",
                )
            target.rmdir()
            return ToolResult(success=True, data=f"Deleted empty directory: {path}")
        else:
            return ToolResult(success=False, data="", error=f"Cannot delete: {path}")
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Delete error: {e}")


# ── Copy File ──────────────────────────────────────────────────────────────────

@registry.tool(
    name="copy_file",
    category="workspace",
    description="Copy a file to a new location",
)
def copy_file(
    source: Annotated[str, "The source file to copy"],
    destination: Annotated[str, "The destination path"],
) -> ToolResult:
    try:
        src = safe_resolve(source)
        dst = safe_resolve(destination)

        if not src.exists():
            return ToolResult(success=False, data="", error=f"Source not found: {source}")
        if not src.is_file():
            return ToolResult(success=False, data="", error=f"Source is not a file: {source}")
        if dst.exists():
            return ToolResult(success=False, data="", error=f"Destination already exists: {destination}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))

        return ToolResult(
            success=True,
            data=f"Copied {source} → {destination}",
            metadata={"source": str(src), "destination": str(dst)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Copy error: {e}")


# ── Diff Files ─────────────────────────────────────────────────────────────────

@registry.tool(
    name="diff_files",
    category="workspace",
    description="Show unified diff between two files",
    idempotent=True,
)
def diff_files(
    path_a: Annotated[str, "The first file to compare"], 
    path_b: Annotated[str, "The second file to compare"], 
    context_lines: Annotated[int, "The number of context lines"] = 3
) -> ToolResult:
    try:
        a = safe_resolve(path_a)
        b = safe_resolve(path_b)

        if not a.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path_a}")
        if not b.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path_b}")

        lines_a = a.read_text(encoding="utf-8").splitlines(keepends=True)
        lines_b = b.read_text(encoding="utf-8").splitlines(keepends=True)

        diff = difflib.unified_diff(
            lines_a, lines_b,
            fromfile=path_a,
            tofile=path_b,
            n=context_lines,
        )
        result = "".join(diff)

        if not result:
            return ToolResult(
                success=True,
                data="Files are identical",
                metadata={"identical": True},
            )

        # Truncate if too large
        if len(result) > config.MAX_TOOL_RESULT_CHARS:
            result = result[: config.MAX_TOOL_RESULT_CHARS] + "\n[DIFF TRUNCATED]"

        return ToolResult(
            success=True,
            data=result,
            metadata={"identical": False},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Diff error: {e}")

