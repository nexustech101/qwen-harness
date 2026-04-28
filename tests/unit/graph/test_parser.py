from pathlib import Path

from graph.parser import parse_python_file


def test_parser_records_signatures_decorators_and_nested_symbols(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text(
        "\n".join(
            [
                "class Service:",
                "    \"\"\"Service doc.\"\"\"",
                "    @classmethod",
                "    def build(cls, name: str = 'x') -> 'Service':",
                "        def inner(value: int) -> int:",
                "            return value",
                "        return cls()",
                "",
                "async def fetch(item_id: int, *, force: bool = False) -> str:",
                "    return str(item_id)",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_python_file(source, tmp_path)

    service = parsed.symbols["sample.py::Service"]
    build = parsed.symbols["sample.py::Service.build"]
    inner = parsed.symbols["sample.py::Service.build.inner"]
    fetch = parsed.symbols["sample.py::fetch"]

    assert service.kind == "class"
    assert service.doc_summary == "Service doc."
    assert build.kind == "method"
    assert build.decorators == ["classmethod"]
    assert "name: str = 'x'" in build.signature
    assert build.return_annotation == "'Service'"
    assert inner.kind == "function"
    assert inner.parent_id == build.id
    assert fetch.kind == "async_function"
    assert any(p.name == "force" and p.kind == "keyword_only" for p in fetch.parameters)


def test_parser_records_imports_and_calls(tmp_path):
    source = tmp_path / "calls.py"
    source.write_text(
        "\n".join(
            [
                "from pkg.mod import helper as h",
                "import os",
                "",
                "def run():",
                "    h()",
                "    os.getcwd()",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_python_file(source, tmp_path)

    assert [item.alias for item in parsed.file.imports] == ["h", "os"]
    assert [call.expression for call in parsed.calls] == ["h", "os.getcwd"]


def test_parser_accepts_utf8_bom(tmp_path):
    source = tmp_path / "bom.py"
    source.write_bytes("\ufeffclass WithBom:\n    pass\n".encode("utf-8"))

    parsed = parse_python_file(source, tmp_path)

    assert parsed.file.syntax_error == ""
    assert "bom.py::WithBom" in parsed.symbols
