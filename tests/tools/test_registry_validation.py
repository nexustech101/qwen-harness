from agent.core.state import ToolResult
from agent.tools.registry import ToolRegistry


def _noop(**_kwargs):
    return ToolResult(success=True, data="ok")


def test_validation_enforces_required_enum_and_unknown_properties():
    reg = ToolRegistry()
    reg.register(
        name="sample",
        fn=_noop,
        category="test",
        description="sample",
        schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["a", "b"]},
                "count": {"type": "integer"},
            },
            "required": ["mode"],
        },
    )

    valid, errors = reg.validate_call("sample", {"mode": "c", "extra": 1})
    assert not valid
    assert any("enum" in e for e in errors)
    assert any("unknown property" in e for e in errors)


def test_alias_name_normalization():
    reg = ToolRegistry()
    reg.register(
        name="read_file",
        fn=_noop,
        category="file",
        description="read",
        schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    )

    valid, errors = reg.validate_call("read_file_content", {"path": "x.py"})
    assert valid
    assert errors == []
