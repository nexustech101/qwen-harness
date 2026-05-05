"""
MCP prompt templates for common workflow patterns.

Import this module as a side effect after `api.mcp.server` has been imported.
"""

from __future__ import annotations

from api.mcp.server import mcp


@mcp.prompt
def code_review(code: str, language: str = "python") -> str:
    """Generate a code review prompt for the given code."""
    return (
        f"Please review the following {language} code for correctness, style, "
        f"potential bugs, and security issues:\n\n```{language}\n{code}\n```"
    )


@mcp.prompt
def explain_error(error: str, context: str = "") -> str:
    """Generate a prompt to explain and fix an error."""
    base = f"Explain the following error and provide a fix:\n\n```\n{error}\n```"
    if context:
        base += f"\n\nContext:\n{context}"
    return base


@mcp.prompt
def generate_tests(code: str, framework: str = "pytest") -> str:
    """Generate a prompt to write unit tests for the given code."""
    return (
        f"Write comprehensive {framework} unit tests for the following code. "
        f"Cover edge cases and error conditions:\n\n```python\n{code}\n```"
    )


@mcp.prompt
def refactor_code(code: str, goal: str) -> str:
    """Generate a prompt to refactor code toward a specific goal."""
    return (
        f"Refactor the following code with this goal: {goal}\n\n"
        f"Preserve existing behaviour and return only the refactored code "
        f"with a brief explanation of changes:\n\n```python\n{code}\n```"
    )
