"""
Tool registry — central catalog of all tools with schema validation.
"""

from __future__ import annotations

import inspect
import functools
from enum import Enum
from typing import Annotated, Any, Callable, Literal, get_args, get_origin, get_type_hints

from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.state import ToolResult


PYTHON_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class ToolEntry:
    """Metadata and callable for a single registered tool."""
    name: str
    fn: Callable[..., ToolResult]
    schema: dict
    category: str
    description: str
    max_retries: int = 0
    idempotent: bool = False


class ToolRegistry:
    """Central registry for all tools with schema validation."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._aliases: dict[str, str] = {
            # Legacy / drifted names seen across model outputs
            "read_file_content": "read_file",
            "write_to_file": "write_file",
            "get_curr_working_dir": "get_working_directory",
            "get_files_in_dir": "list_directory",
            "search_files": "grep_workspace",
            "workspace_search": "grep_workspace",
            "run_shell_command": "run_command",
            "file_read": "read_file",
            "file_write": "write_file",
            "edit": "edit_file",
        }

    # ── Registration ───────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: Callable[..., ToolResult],
        schema: dict,
        category: str,
        description: str,
        max_retries: int = 0,
        idempotent: bool = False,
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name, fn=fn, schema=schema, category=category,
            description=description, max_retries=max_retries, idempotent=idempotent,
        )

    def tool(
        self,
        name: str,
        category: str,
        description: str,
        max_retries: int = 0,
        idempotent: bool = False,
    ) -> Callable:
        """
        Decorator that registers a tool and auto-generates its JSON schema
        from the function signature. Use Annotated[type, "description"] on
        parameters to embed per-field descriptions inline.

        Example:
            @registry.tool(name="read_file", category="file", description="Read a file")
            def read_file(
                path: Annotated[str, "Relative or absolute file path"],
                start_line: Annotated[int, "1-based start line (inclusive). Omit for beginning."] = None,
                end_line: Annotated[int, "1-based end line (inclusive). Omit for end of file."] = None,
            ) -> ToolResult:
                ...
        """
        def decorator(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
            schema = self._build_schema_from_signature(fn)
            self.register(
                name=name, fn=fn, schema=schema, category=category,
                description=description, max_retries=max_retries, idempotent=idempotent,
            )
            return fn
        return decorator

    def _build_schema_from_signature(self, fn: Callable) -> dict:
        """Build a JSON Schema object from a function's annotated signature."""
        hints = get_type_hints(fn, include_extras=True)  # include_extras preserves Annotated
        sig = inspect.signature(fn)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            annotation = hints.get(param_name, str)
            properties[param_name] = self._resolve_type(annotation)

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            **({"required": required} if required else {}),
        }
    
    def _resolve_type(self, annotation) -> dict:
        """Recursively resolve a Python type annotation into a JSON Schema fragment."""

        # Annotated[type, "description"] — unwrap and recurse on the inner type
        if get_origin(annotation) is Annotated:
            inner, *metadata = get_args(annotation)
            schema = self._resolve_type(inner)
            # First string in metadata is treated as the description
            for meta in metadata:
                if isinstance(meta, str):
                    schema["description"] = meta
                    break
            return schema

        # Literal["a", "b"] → enum
        if get_origin(annotation) is Literal:
            values = get_args(annotation)
            base_type = PYTHON_TO_JSON_TYPE.get(type(values[0]), "string")
            return {"type": base_type, "enum": list(values)}

        # list[str] → array with items
        if get_origin(annotation) is list:
            args = get_args(annotation)
            schema = {"type": "array"}
            if args:
                schema["items"] = self._resolve_type(args[0])
            return schema

        # Enum subclass → enum values
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            values = [e.value for e in annotation]
            base_type = PYTHON_TO_JSON_TYPE.get(type(values[0]), "string")
            return {"type": base_type, "enum": values}

        return {"type": PYTHON_TO_JSON_TYPE.get(annotation, "string")}

    # ── Lookup ─────────────────────────────────────────────────────────────────

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(self.normalize_name(name))

    def __contains__(self, name: str) -> bool:
        return self.normalize_name(name) in self._tools

    def normalize_name(self, name: str) -> str:
        """Normalize a model-produced tool name via alias table."""
        n = str(name or "").strip()
        return self._aliases.get(n, n)

    def register_alias(self, alias: str, canonical: str) -> None:
        """Register an additional alias mapping."""
        if canonical in self._tools:
            self._aliases[alias] = canonical

    def list_tools(self, category: str | None = None) -> list[ToolEntry]:
        entries = list(self._tools.values())
        if category:
            entries = [e for e in entries if e.category == category]
        return sorted(entries, key=lambda e: e.name)

    # ── Validation ─────────────────────────────────────────────────────────────

    def validate_call(self, name: str, args: dict) -> tuple[bool, list[str]]:
        """Validate arguments against the tool's JSON schema."""
        canonical = self.normalize_name(name)
        entry = self._tools.get(canonical)
        if not entry:
            return False, [f"Unknown tool: {name}"]

        if not isinstance(args, dict):
            return False, [f"Tool '{canonical}' arguments must be an object"]

        errors = _validate_schema(args, entry.schema, "$")

        return len(errors) == 0, errors

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute(self, name: str, args: dict) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        canonical = self.normalize_name(name)
        entry = self._tools.get(canonical)
        if not entry:
            return ToolResult(success=False, data="", error=f"Unknown tool: {name}")

        try:
            return entry.fn(**args)
        except TypeError as e:
            return ToolResult(success=False, data="", error=f"Bad arguments for {canonical}: {e}")
        except Exception as e:
            return ToolResult(success=False, data="", error=f"Error executing {canonical}: {e}")

    # ── Format Conversion ──────────────────────────────────────────────────────

    def to_ollama_format(
        self,
        categories: list[str] | None = None,
        names: set[str] | None = None,
    ) -> list[dict]:
        """Convert registered tools to Ollama's expected function-call format."""
        tools = []
        for entry in self._tools.values():
            if categories and entry.category not in categories:
                continue
            if names and entry.name not in names:
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": entry.name,
                    "description": entry.description,
                    "parameters": entry.schema,
                },
            })
        return tools

    def to_prompt_format(
        self,
        categories: list[str] | None = None,
        names: set[str] | None = None,
    ) -> str:
        """Human-readable tool list for system prompts."""
        lines = []
        eligible = []
        for entry in self._tools.values():
            if categories and entry.category not in categories:
                continue
            if names and entry.name not in names:
                continue
            eligible.append(entry)
        for i, entry in enumerate(sorted(eligible, key=lambda e: e.name), 1):
            params = entry.schema.get("properties", {})
            required = set(entry.schema.get("required", []))
            param_strs = []
            for pname in params:
                suffix = "" if pname in required else "?"
                param_strs.append(f"{pname}{suffix}")
            sig = ", ".join(param_strs)
            lines.append(f"{i}. {entry.name}({sig}) — {entry.description}")
        return "\n".join(lines)

    def filter(self, categories: list[str]) -> "ToolRegistry":
        """Return a new registry containing only tools from the given categories."""
        filtered = ToolRegistry()
        for entry in self._tools.values():
            if entry.category in categories:
                filtered._tools[entry.name] = entry
        filtered._aliases = dict(self._aliases)
        return filtered


def _check_type(value: Any, expected: str) -> bool:
    """Basic JSON-schema type checking."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected_types = type_map.get(expected)
    if expected_types is None:
        return True  # Unknown type, allow
    return isinstance(value, expected_types)


def _validate_schema(value: Any, schema: dict, path: str) -> list[str]:
    """Validate a JSON-like value against a subset of JSON schema."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and not _check_type(value, expected_type):
        errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
        return errors

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(f"{path}: value {value!r} not in enum {enum!r}")
        return errors

    if expected_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get(
            "additionalProperties",
            True if not properties else False,
        )
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object")
            return errors
        for req in required:
            if req not in value:
                errors.append(f"{path}.{req}: missing required property")
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate_schema(item, properties[key], f"{path}.{key}"))
            elif additional is False:
                errors.append(f"{path}.{key}: unknown property")
        return errors

    if expected_type == "array":
        items_schema = schema.get("items", {})
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
            return errors
        for i, item in enumerate(value):
            errors.extend(_validate_schema(item, items_schema, f"{path}[{i}]"))
        return errors

    return errors


# ── Global registry instance ───────────────────────────────────────────────────
registry = ToolRegistry()

