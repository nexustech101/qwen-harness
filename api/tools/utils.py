"""
Shared path validation — confines all tool paths to the project root (CWD).

Absolute paths like /flask-app are treated as relative to CWD, not the
filesystem root.  Traversal via .. is blocked if it escapes CWD.
Symlinks are resolved to their real target and re-validated.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


def _check_within_root(resolved: Path, root: Path, original: str) -> Path:
    """Verify *resolved* is within *root*, including after symlink resolution."""
    try:
        resolved.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Path escapes project directory: {original!r} resolved to {resolved}"
        )

    # Follow symlinks to their real target and re-validate.  Path.resolve()
    # already follows symlinks, but a symlink created *after* the first
    # resolve (or a chain of symlinks) could still escape.
    real = Path(os.path.realpath(resolved))
    try:
        real.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Symlink target escapes project directory: {original!r} → {real}"
        )

    return resolved


def safe_resolve(path: str) -> Path:
    """Resolve *path* so it always stays within the current working directory.

    Rules:
    1. If the path is already an absolute path within CWD, accept it directly.
    2. Strip leading ``/`` or ``\\`` and drive letters so the LLM can't escape.
    3. Resolve relative to CWD.
    4. Reject the result if it escapes CWD (e.g. via ``..``).
    5. Reject the result if a symlink target escapes CWD.
    """
    cwd = Path.cwd().resolve()

    # First, try resolving the raw path — if it's already absolute and inside
    # CWD (e.g. "C:\Users\...\project\flask-app\app.py"), just use it.
    raw = Path(path.replace("/", "\\") if "\\" in path or ":" in path else path)
    if raw.is_absolute():
        resolved = raw.resolve()
        try:
            return _check_within_root(resolved, cwd, path)
        except PermissionError:
            pass  # Falls through to the stripping logic below

    # Normalise to forward-slash for consistent handling, then strip leading
    # slashes so "/flask-app" becomes "flask-app".
    cleaned = path.replace("\\", "/").lstrip("/")

    # Also strip Windows drive letters the LLM might hallucinate (e.g. "C:/foo")
    posix = PurePosixPath(cleaned)
    if len(posix.parts) > 0 and len(posix.parts[0]) == 2 and posix.parts[0][1] == ":":
        cleaned = "/".join(posix.parts[1:])

    resolved = (cwd / cleaned).resolve()

    return _check_within_root(resolved, cwd, path)

