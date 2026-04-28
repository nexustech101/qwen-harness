"""
System tools — working directory, logging, command execution.
"""

from __future__ import annotations

import os
import shlex
import subprocess

from pathlib import Path
from typing import Annotated, Literal
from datetime import datetime

from app import config
from app.core.state import ToolResult
from app.tools.registry import registry
from app.tools.utils import safe_resolve


@registry.tool(
    name="get_working_directory",
    category="system",
    description="Get the current working directory",
    idempotent=True,
)
def get_working_directory() -> ToolResult:
    try:
        cwd = os.getcwd()
        return ToolResult(success=True, data=cwd)
    except Exception as e:
        return ToolResult(success=False, data="", error=str(e))


@registry.tool(
    name="log_message",
    category="system",
    description="Write a timestamped message to the agent log file",
)
def log_message(
    message: Annotated[str, "The message to log"],
    level: Annotated[str, "The log level"] = "INFO",
) -> ToolResult:
    try:
        entry = f"[{datetime.now().isoformat()}] [{level}] {message}\n"
        log_path = Path(config.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return ToolResult(
            success=True,
            data=f"Logged: {entry.strip()}",
        )
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Logging error: {e}")


# Allowlist of safe command prefixes.
#
# Threat model: the LLM is semi-trusted — the allowlist prevents obviously
# wrong commands (rm -rf /, shutdown, etc.) but does NOT prevent all abuse.
# Commands like `python -c "..."` or `curl` with SSRF payloads can still
# cause harm.  For untrusted models, run the agent in a sandboxed container.
_COMMAND_ALLOWLIST = {
    # Core / shell
    "python", "python3", "pip", "pip3", "git", "ls", "dir", "cat",
    "head", "tail", "echo", "find", "grep", "wc", "sort", "type",
    "where", "which", "touch", "mkdir", "cp", "mv", "rm", "chmod",
    "tar", "zip", "unzip", "curl", "wget",
    # Python ecosystem
    "pytest", "mypy", "ruff", "black", "flake8", "isort", "bandit",
    # JavaScript / TypeScript
    "node", "npm", "npx", "yarn", "pnpm", "tsc", "eslint", "prettier",
    # Other languages / build tools
    "cargo", "rustc", "go", "make", "cmake", "dotnet", "javac", "java",
    "mvn", "gradle",
    # Container
    "docker", "docker-compose",
    # PowerShell
    "Get-ChildItem", "Get-Content", "Get-Location", "Test-Path",
    "Select-String", "Invoke-WebRequest",
}


@registry.tool(
    name="run_command",
    category="system",
    description="Run a shell command (restricted to safe commands)",
)
def run_command(
    command: Annotated[str, "The command to run"],
    timeout: Annotated[int, "The timeout in seconds"] = 30,
    working_dir: Annotated[str | None, "The working directory"] = None,
) -> ToolResult:
    try:
        # Security: check command against allowlist
        parts = shlex.split(command)
        if not parts:
            return ToolResult(success=False, data="", error="Empty command")

        # Check if base command is in list of allowed commands
        # Use Path(...).stem to extract the command name from command string
        base_cmd = Path(parts[0]).stem
        if base_cmd not in _COMMAND_ALLOWLIST:
            return ToolResult(
                success=False, data="",
                error=f"Command not allowed: {base_cmd}. Allowed: {', '.join(sorted(_COMMAND_ALLOWLIST))}",
            )

        # Run the command because checks passed
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

        # Truncate large output
        max_output = 250_000
        if len(output) > max_output:
            output = output[:max_output] + f"\n[TRUNCATED at {max_output} chars]"

        return ToolResult(
            success=result.returncode == 0,
            data=output,
            metadata={"returncode": result.returncode},
            error=f"Exit code {result.returncode}" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, data="", error=f"Command timed out after {timeout}s")
    except FileNotFoundError:
        return ToolResult(success=False, data="", error=f"Command not found: {parts[0]}")
    except Exception as e:
        return ToolResult(success=False, data="", error=f"Command error: {e}")
