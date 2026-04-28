from app.response.response_parser import ResponseParser


def test_structured_json_with_status_and_tools():
    parser = ResponseParser(known_tools={"write_file"})
    raw = (
        "```json\n"
        '{"reasoning":"r","tools":[{"name":"write_file","arguments":{"path":"a.py","content":"x"}}],'
        '"status":"in-progress","response":""}'
        "\n```"
    )

    result = parser.parse(raw)

    assert result.mode == "structured"
    assert result.status == "in-progress"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "write_file"
    assert result.tool_calls[0].arguments["path"] == "a.py"


def test_top_level_array_normalization():
    parser = ResponseParser(known_tools={"echo_tool", "second_tool"})
    raw = '[{"name":"echo_tool","arguments":{"message":"one"}},{"name":"second_tool","arguments":{"value":"two"}}]'

    result = parser.parse(raw)

    assert result.mode == "array"
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].name == "echo_tool"
    assert result.tool_calls[1].name == "second_tool"


def test_repaired_json_trailing_comma_sets_diagnostic():
    parser = ResponseParser(known_tools={"echo_tool"})
    raw = '{"name":"echo_tool","arguments":{"message":"hi",},}'

    result = parser.parse(raw)

    assert result.mode == "legacy"
    assert result.diagnostics.get("repair_applied") is True
    assert result.tool_calls[0].name == "echo_tool"


def test_stream_thinking_and_think_tags_are_merged():
    parser = ResponseParser(known_tools={"echo_tool"})
    raw = '<think>tag-thought</think>{"name":"echo_tool","arguments":{"message":"hi"}}'

    result = parser.parse(raw, stream_thinking="stream-thought")

    assert result.mode == "legacy"
    assert "stream-thought" in result.reasoning
    assert "tag-thought" in result.reasoning
