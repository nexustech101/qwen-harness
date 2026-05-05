from pathlib import Path

import pytest

from graph.cache import file_hash, load_cached, save_cached
from graph.detect import detect
from graph.security import sanitize_label, validate_graph_path, validate_url
from graph.validate import validate_extraction


def test_detect_respects_ignore_and_sensitive_files(tmp_path):
    (tmp_path / ".graphifyignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("def kept():\n    return 1\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("def ignored():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    result = detect(tmp_path)

    assert str(tmp_path / "kept.py") in result["files"]["code"]
    assert str(tmp_path / "ignored.py") not in result["files"]["code"]
    assert all(".env" not in item for item in result["files"]["code"])


def test_cache_uses_file_content_and_relative_path(tmp_path):
    source = tmp_path / "a.py"
    source.write_text("def a():\n    return 1\n", encoding="utf-8")
    payload = {"nodes": [{"id": "a"}], "edges": []}

    save_cached(source, payload, tmp_path)

    assert load_cached(source, tmp_path) == payload
    first_hash = file_hash(source, tmp_path)
    source.write_text("def a():\n    return 2\n", encoding="utf-8")
    assert file_hash(source, tmp_path) != first_hash
    assert load_cached(source, tmp_path) is None


def test_validate_and_security_helpers(tmp_path):
    errors = validate_extraction({"nodes": [{"id": "a"}], "edges": [{"source": "a"}]})

    assert errors
    assert sanitize_label("ok\x00" + "x" * 300).startswith("ok")
    with pytest.raises(ValueError):
        validate_url("file:///etc/passwd")

    graph_dir = tmp_path / ".graph-out"
    graph_dir.mkdir()
    graph_file = graph_dir / "graph.json"
    graph_file.write_text("{}", encoding="utf-8")
    assert validate_graph_path(graph_file, graph_dir) == graph_file.resolve()
    with pytest.raises(ValueError):
        validate_graph_path(Path(tmp_path / "outside.json"), graph_dir)
