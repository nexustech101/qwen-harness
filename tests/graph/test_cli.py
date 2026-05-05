import subprocess
import sys


def test_graphify_help_does_not_refresh(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "graph", "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage: graphify" in result.stdout
    assert not (tmp_path / ".graph-out").exists()
