import json
from pathlib import Path

from app import config
from app.core.workspace import Workspace


def _set_workspace_env(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "central-workspace"
    projects = home / "workspaces"
    index = home / "workspace_index.json"
    monkeypatch.setattr(config, "WORKSPACE_HOME", str(home))
    monkeypatch.setattr(config, "WORKSPACE_PROJECTS_DIR", str(projects))
    monkeypatch.setattr(config, "WORKSPACE_INDEX_FILE", str(index))
    return home


def test_workspace_is_central_and_registered(tmp_path, monkeypatch):
    home = _set_workspace_env(tmp_path, monkeypatch)
    project_root = tmp_path / "sample-project"
    project_root.mkdir()

    ws = Workspace(project_root=project_root)
    ws.ensure_exists()

    assert ws.root.parent == home / "workspaces"
    assert ws.project_name == "sample-project"
    assert ws.workspace_key.startswith("sample-project-")

    index_file = home / "workspace_index.json"
    assert index_file.exists()
    data = json.loads(index_file.read_text(encoding="utf-8"))
    entry = data["projects"][str(project_root.resolve())]
    assert entry["project_name"] == "sample-project"
    assert entry["workspace_key"] == ws.workspace_key

    resolved = Workspace.resolve_by_project_name("sample-project")
    assert resolved is not None
    assert resolved["workspace_key"] == ws.workspace_key
    assert Path(resolved["workspace_path"]) == ws.root


def test_session_upload_dir_is_under_central_workspace(tmp_path, monkeypatch):
    _set_workspace_env(tmp_path, monkeypatch)
    project_root = tmp_path / "repo"
    project_root.mkdir()

    ws = Workspace(project_root=project_root)
    upload_dir = ws.session_upload_dir("session-123")

    assert upload_dir == ws.root / "uploads" / "session-123"
    assert upload_dir.exists()
