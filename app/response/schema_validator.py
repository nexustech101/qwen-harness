"""
Schema validator — validates tool calls against the tool registry.
"""

from __future__ import annotations

from app.core.state import ValidationResult
from app.core.state import ToolCall
from app.tools.registry import ToolRegistry


class SchemaValidator:
    """Validate parsed tool calls against the registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def validate(self, tool_calls: list[ToolCall]) -> ValidationResult:
        """Validate a list of tool calls. Returns aggregated result."""
        errors: list[str] = []
        schema_mismatch = False

        for call in tool_calls:
            name = call.name
            args = call.arguments

            # Tool existence
            if name not in self._registry:
                available = ", ".join(
                    t.name for t in self._registry.list_tools()
                )
                errors.append(
                    f"Unknown tool: '{name}'. Available: {available}"
                )
                schema_mismatch = True
                continue

            # Argument validation
            valid, arg_errors = self._registry.validate_call(name, args)
            if not valid:
                errors.extend(arg_errors)
                schema_mismatch = True

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            schema_mismatch=schema_mismatch,
        )
