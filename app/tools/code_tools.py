"""
Code quality tools — syntax checking, test running, patch application.

These tools let agents validate their own work: check for syntax errors,
run tests to verify correctness, and apply unified diffs.
"""

from __future__ import annotations

import ast
import re
import sys
import subprocess

from pathlib import Path
from typing import Annotated, Literal

from app import config
from app.core.state import ToolResult
from app.tools.registry import registry
from app.tools.utils import safe_resolve


# ── Check Syntax ───────────────────────────────────────────────────────────────

@registry.tool(
    name="check_syntax",
    category="code",
    description="Check a Python file for syntax errors without executing it",
)
def check_syntax(path: Annotated[str, "The path to the Python file to check for syntax errors"]) -> ToolResult:
    try:
        target = safe_resolve(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")
        if not target.is_file():
            return ToolResult(success=False, data="", error=f"Not a file: {path}")

        source = target.read_text(encoding="utf-8")

        try:
            ast.parse(source, filename=str(target))
        except SyntaxError as e:
            return ToolResult(
                success=True,
                data=f"Syntax error in {path}:{e.lineno}: {e.msg}",
                metadata={
                    "valid": False,
                    "line": e.lineno,
                    "offset": e.offset,
                    "message": e.msg,
                },
            )

        return ToolResult(
            success=True,
            data=f"No syntax errors in {path}",
            metadata={"valid": True},
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Syntax check error: {e}")


# ── Run Tests ──────────────────────────────────────────────────────────────────

@registry.tool(
    name="run_tests",
    category="code",
    description="Run tests with pytest or unittest and return results",
)
def run_tests(
    path: Annotated[str, "The path to the test file or directory to run"],
    framework: Annotated[str, "The test framework to use ('pytest' or 'unittest')"] = "pytest",
    timeout: Annotated[int, "The maximum time in seconds to allow the test run"] = 60,
) -> ToolResult:
    try:
        timeout = min(timeout, 120)  # Cap at 2 minutes

        if framework == "pytest":
            cmd = [sys.executable, "-m", "pytest", path, "-v", "--tb=short", "--no-header", "-q"]
        elif framework == "unittest":
            cmd = [sys.executable, "-m", "unittest", path, "-v"]
        else:
            return ToolResult(
                success=False, data="",
                error=f"Unknown framework: {framework}. Use 'pytest' or 'unittest'.",
            )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.cwd()),
        )

        output = result.stdout
        if result.stderr:
            # Filter out common pytest noise
            stderr_lines = [
                line for line in result.stderr.splitlines()
                if not line.startswith(("=", "-", "platform ", "rootdir:", "configfile:"))
            ]
            if stderr_lines:
                output += "\n[STDERR]\n" + "\n".join(stderr_lines)

        # Truncate if too large
        if len(output) > config.MAX_TOOL_RESULT_CHARS:
            output = output[: config.MAX_TOOL_RESULT_CHARS] + "\n[OUTPUT TRUNCATED]"

        passed = result.returncode == 0
        return ToolResult(
            success=True,  # Tool succeeded even if tests failed
            data=output,
            metadata={
                "tests_passed": passed,
                "returncode": result.returncode,
            },
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False, data="",
            error=f"Tests timed out after {timeout}s",
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Test run error: {e}")


# ── Apply Patch ────────────────────────────────────────────────────────────────

@registry.tool(
    name="apply_patch",
    category="code",
    description="Apply a unified diff patch to a file",
)
def apply_patch(
    path: Annotated[str, "The path to the file to apply the patch to"],
    patch: Annotated[str, "The unified diff patch to apply"],
) -> ToolResult:
    """Apply a unified diff to a file.

    Supports standard unified diff format:
        @@ -start,count +start,count @@
        -removed line
        +added line
         context line
    """
    try:
        target = safe_resolve(path)
        if not target.exists():
            return ToolResult(success=False, data="", error=f"File not found: {path}")

        original = target.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)

        # Parse hunks from the patch
        hunks = _parse_unified_diff(patch)
        if not hunks:
            return ToolResult(
                success=False, data="",
                error="Could not parse patch — must be in unified diff format",
            )

        # Apply hunks in reverse order to preserve line numbers
        result_lines = list(lines)
        for hunk in reversed(hunks):
            start = hunk["start"] - 1  # 0-indexed
            removed = hunk["removed"]
            added = hunk["added"]

            # Verify context matches
            for i, rem_line in enumerate(removed):
                if start + i >= len(result_lines):
                    return ToolResult(
                        success=False, data="",
                        error=f"Patch does not match file at line {start + i + 1}",
                    )
                if result_lines[start + i].rstrip("\n") != rem_line.rstrip("\n"):
                    return ToolResult(
                        success=False, data="",
                        error=(
                            f"Patch context mismatch at line {start + i + 1}:\n"
                            f"  expected: {rem_line.rstrip()}\n"
                            f"  actual:   {result_lines[start + i].rstrip()}"
                        ),
                    )

            # Apply: delete old lines, insert new
            del result_lines[start: start + len(removed)]
            for i, add_line in enumerate(added):
                if not add_line.endswith("\n"):
                    add_line += "\n"
                result_lines.insert(start + i, add_line)

        new_content = "".join(result_lines)

        # Write atomically
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(new_content, encoding="utf-8")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        return ToolResult(
            success=True,
            data=f"Applied {len(hunks)} hunk(s) to {path}",
            metadata={"hunks": len(hunks)},
        )
    except PermissionError as e:
        return ToolResult(success=False, data="", error=str(e))
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Patch error: {e}")


def _parse_unified_diff(patch: Annotated[str, "The unified diff patch to parse"]) -> list[dict]:
    """Parse a unified diff into a list of hunks.

    Each hunk: {"start": int, "removed": [str], "added": [str]}
    """
    hunks: list[dict] = []
    hunk_header = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")

    current_hunk = None
    for rawline in patch.splitlines(keepends=True):
        line = rawline.rstrip("\r\n")
        m = hunk_header.match(line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {
                "start": int(m.group(1)),
                "removed": [],
                "added": [],
            }
        elif current_hunk is not None:
            if line.startswith("-"):
                current_hunk["removed"].append(line[1:])
            elif line.startswith("+"):
                current_hunk["added"].append(line[1:])
            elif line.startswith(" "):
                # Context line: part of both removed and added
                current_hunk["removed"].append(line[1:])
                current_hunk["added"].append(line[1:])

    if current_hunk:
        hunks.append(current_hunk)

    return hunks
