"""
Workspace-wide tools — search across project, file management ops.
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.tools.utils import safe_resolve

MAX_TOOL_RESULT_CHARS = 50_000

_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".eggs", ".graph-out", "graph", "docs", "tests", "test", "examples", 
    "sample_data",
}

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
    return name in _SKIP_DIRS or name.startswith(".")


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() not in _BINARY_EXTS


def _walk_files(root: Path, include: str | None = None, exclude: str | None = None) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(root))
            if include and not fnmatch.fnmatch(rel, include) and not fnmatch.fnmatch(fname, include):
                continue
            if exclude and (fnmatch.fnmatch(rel, exclude) or fnmatch.fnmatch(fname, exclude)):
                continue
            files.append(fpath)
    return files


@tool
def grep_workspace(
    pattern: Annotated[str, "Text pattern or regex to search for"],
    is_regex: Annotated[bool, "Whether the pattern is a regular expression"] = False,
    include: Annotated[str | None, "Glob pattern to include files"] = None,
    exclude: Annotated[str | None, "Glob pattern to exclude files"] = None,
    max_results: Annotated[int, "Maximum number of results"] = 100,
) -> str:
    """Search for a text pattern across all project files. Returns file:line:match."""
    try:
        root = Path.cwd().resolve()
        files = _walk_files(root, include, exclude)
        if is_regex:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                return f"ERROR: Invalid regex: {exc}"
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
                hit = compiled.search(line) if compiled else pattern.lower() in line.lower()
                if hit:
                    rel = fpath.relative_to(root)
                    matches.append(f"{rel}:{i}: {line.rstrip()}")
            if len(matches) >= max_results:
                break
        if not matches:
            return f"No matches for '{pattern}' across {files_searched} files"
        result = "\n".join(matches)
        if len(matches) >= max_results:
            result += f"\n\n[CAPPED at {max_results} results — use include/exclude to narrow]"
        return result
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def find_files(
    pattern: Annotated[str, "Filename or glob pattern to search for"],
    path: Annotated[str, "Directory to search in"] = ".",
    max_results: Annotated[int, "Maximum number of results"] = 50,
) -> str:
    """Find files by name or glob pattern across the workspace."""
    try:
        root = safe_resolve(path)
        if not root.exists():
            return f"ERROR: Directory not found: {path}"
        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for fname in filenames:
                if len(results) >= max_results:
                    break
                fpath = Path(dirpath) / fname
                rel = str(fpath.relative_to(root))
                if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(rel, pattern) or pattern.lower() in fname.lower():
                    results.append(rel)
            if len(results) >= max_results:
                break
        if not results:
            return f"No files matching '{pattern}'"
        return "\n".join(sorted(results))
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def create_directory(path: Annotated[str, "Directory path to create"]) -> str:
    """Create a directory (and parent directories)."""
    try:
        target = safe_resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {path}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def move_file(
    source: Annotated[str, "Source file or directory to move"],
    destination: Annotated[str, "Destination path"],
) -> str:
    """Move or rename a file or directory."""
    try:
        src = safe_resolve(source)
        dst = safe_resolve(destination)
        if not src.exists():
            return f"ERROR: Source not found: {source}"
        if dst.exists():
            return f"ERROR: Destination already exists: {destination}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {source} to {destination}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def delete_file(path: Annotated[str, "File or empty directory to delete"]) -> str:
    """Delete a file or empty directory."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return f"ERROR: Not found: {path}"
        if target.is_file():
            target.unlink()
            return f"Deleted file: {path}"
        elif target.is_dir():
            children = list(target.iterdir())
            if children:
                return f"ERROR: Directory not empty ({len(children)} items): {path}"
            target.rmdir()
            return f"Deleted empty directory: {path}"
        return f"ERROR: Cannot delete: {path}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def copy_file(
    source: Annotated[str, "Source file to copy"],
    destination: Annotated[str, "Destination path"],
) -> str:
    """Copy a file to a new location."""
    try:
        src = safe_resolve(source)
        dst = safe_resolve(destination)
        if not src.exists():
            return f"ERROR: Source not found: {source}"
        if not src.is_file():
            return f"ERROR: Source is not a file: {source}"
        if dst.exists():
            return f"ERROR: Destination already exists: {destination}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return f"Copied {source} to {destination}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def diff_files(
    path_a: Annotated[str, "First file to compare"],
    path_b: Annotated[str, "Second file to compare"],
    context_lines: Annotated[int, "Number of context lines"] = 3,
) -> str:
    """Show unified diff between two files."""
    try:
        a = safe_resolve(path_a)
        b = safe_resolve(path_b)
        if not a.exists():
            return f"ERROR: File not found: {path_a}"
        if not b.exists():
            return f"ERROR: File not found: {path_b}"
        lines_a = a.read_text(encoding="utf-8").splitlines(keepends=True)
        lines_b = b.read_text(encoding="utf-8").splitlines(keepends=True)
        diff = difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=path_b, n=context_lines)
        result = "".join(diff)
        if not result:
            return "Files are identical"
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = result[:MAX_TOOL_RESULT_CHARS] + "\n[DIFF TRUNCATED]"
        return result
    except Exception as exc:
        return f"ERROR: {exc}"