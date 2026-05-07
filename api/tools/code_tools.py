"""
Code quality tools — syntax checking, test running, patch application.
"""

from __future__ import annotations

import ast
import re
import sys
import subprocess

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.tools.utils import safe_resolve

MAX_TOOL_RESULT_CHARS = 50_000


@tool
def check_syntax(path: Annotated[str, "Path to the Python file to check"]) -> str:
    """Check a Python file for syntax errors without executing it."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        if not target.is_file():
            return f"ERROR: Not a file: {path}"
        source = target.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(target))
        except SyntaxError as exc:
            return f"Syntax error in {path}:{exc.lineno}: {exc.msg}"
        return f"No syntax errors in {path}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def run_tests(
    path: Annotated[str, "Path to the test file or directory"],
    framework: Annotated[str, "Test framework: 'pytest' or 'unittest'"] = "pytest",
    timeout: Annotated[int, "Timeout in seconds (max 120)"] = 60,
) -> str:
    """Run tests with pytest or unittest and return results."""
    try:
        timeout = min(timeout, 120)
        if framework == "pytest":
            cmd = [sys.executable, "-m", "pytest", path, "-v", "--tb=short", "--no-header", "-q"]
        elif framework == "unittest":
            cmd = [sys.executable, "-m", "unittest", path, "-v"]
        else:
            return f"ERROR: Unknown framework: {framework}. Use 'pytest' or 'unittest'."
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(Path.cwd()))
        output = result.stdout
        if result.stderr:
            stderr_lines = [
                line for line in result.stderr.splitlines()
                if not line.startswith(("=", "-", "platform ", "rootdir:", "configfile:"))
            ]
            if stderr_lines:
                output += "\n[STDERR]\n" + "\n".join(stderr_lines)
        if len(output) > MAX_TOOL_RESULT_CHARS:
            output = output[:MAX_TOOL_RESULT_CHARS] + "\n[OUTPUT TRUNCATED]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Tests timed out after {timeout}s"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def apply_patch(
    path: Annotated[str, "Path to the file to patch"],
    patch: Annotated[str, "Unified diff patch to apply"],
) -> str:
    """Apply a unified diff patch to a file."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return f"ERROR: File not found: {path}"
        original = target.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        hunks = _parse_unified_diff(patch)
        if not hunks:
            return "ERROR: Could not parse patch — must be in unified diff format"
        result_lines = list(lines)
        for hunk in reversed(hunks):
            start = hunk["start"] - 1
            removed = hunk["removed"]
            added = hunk["added"]
            for i, rem_line in enumerate(removed):
                if start + i >= len(result_lines):
                    return f"ERROR: Patch does not match file at line {start + i + 1}"
                if result_lines[start + i].rstrip("\n") != rem_line.rstrip("\n"):
                    return (
                        f"ERROR: Patch context mismatch at line {start + i + 1}:\n"
                        f"  expected: {rem_line.rstrip()}\n"
                        f"  actual:   {result_lines[start + i].rstrip()}"
                    )
            del result_lines[start: start + len(removed)]
            for i, add_line in enumerate(added):
                if not add_line.endswith("\n"):
                    add_line += "\n"
                result_lines.insert(start + i, add_line)
        new_content = "".join(result_lines)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(new_content, encoding="utf-8")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return f"Applied {len(hunks)} hunk(s) to {path}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


def _parse_unified_diff(patch: str) -> list[dict]:
    hunks: list[dict] = []
    hunk_header = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
    current_hunk = None
    for rawline in patch.splitlines(keepends=True):
        line = rawline.rstrip("\r\n")
        m = hunk_header.match(line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {"start": int(m.group(1)), "removed": [], "added": []}
        elif current_hunk is not None:
            if line.startswith("-"):
                current_hunk["removed"].append(line[1:])
            elif line.startswith("+"):
                current_hunk["added"].append(line[1:])
            elif line.startswith(" "):
                current_hunk["removed"].append(line[1:])
                current_hunk["added"].append(line[1:])
    if current_hunk:
        hunks.append(current_hunk)
    return hunks