"""
System tools — working directory and command execution.
"""

from __future__ import annotations

import os
import shlex
import subprocess

from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.tools.utils import safe_resolve

# Allowlist of safe command prefixes.
_COMMAND_ALLOWLIST = {
    "python", "python3", "pip", "pip3", "git", "ls", "dir", "cat",
    "head", "tail", "echo", "find", "grep", "wc", "sort", "type",
    "where", "which", "touch", "mkdir", "cp", "mv", "rm", "chmod",
    "tar", "zip", "unzip", "curl", "wget",
    "pytest", "mypy", "ruff", "black", "flake8", "isort", "bandit",
    "node", "npm", "npx", "yarn", "pnpm", "tsc", "eslint", "prettier",
    "cargo", "rustc", "go", "make", "cmake", "dotnet", "javac", "java",
    "mvn", "gradle",
    "docker", "docker-compose",
    "Get-ChildItem", "Get-Content", "Get-Location", "Test-Path",
    "Select-String", "Invoke-WebRequest",
}


@tool
def get_working_directory() -> str:
    """Get the current working directory."""
    try:
        return os.getcwd()
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def run_command(
    command: Annotated[str, "Shell command to run"],
    timeout: Annotated[int, "Timeout in seconds (max 60)"] = 30,
    working_dir: Annotated[str | None, "Working directory (default: cwd)"] = None,
) -> str:
    """Run a shell command. Restricted to an allowlist of safe commands."""
    try:
        parts = shlex.split(command)
        if not parts:
            return "ERROR: Empty command"
        base_cmd = Path(parts[0]).stem
        if base_cmd not in _COMMAND_ALLOWLIST:
            allowed = ", ".join(sorted(_COMMAND_ALLOWLIST))
            return f"ERROR: Command not allowed: {base_cmd}. Allowed: {allowed}"
        cwd = str(safe_resolve(working_dir)) if working_dir else os.getcwd()
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=min(timeout, 60),
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        max_output = 250_000
        if len(output) > max_output:
            output = output[:max_output] + f"\n[TRUNCATED at {max_output} chars]"
        if result.returncode != 0:
            output += f"\n[Exit code {result.returncode}]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except FileNotFoundError:
        parts = shlex.split(command)
        return f"ERROR: Command not found: {parts[0] if parts else command}"
    except Exception as exc:
        return f"ERROR: {exc}"