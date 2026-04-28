from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 50 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10
UPLOAD_CHUNK_SIZE = 1024 * 1024

ALLOWED_MIME_PREFIXES = ("image/", "text/")
ALLOWED_MIME_TYPES = {
    "application/json",
    "application/pdf",
    "application/xml",
    "application/javascript",
    "application/typescript",
    "application/x-yaml",
    "application/x-toml",
    "application/sql",
    "application/x-sh",
    "application/x-python",
}
BLOCKED_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bat",
    ".cmd",
    ".com",
    ".msi",
    ".scr",
    ".pif",
    ".ps1",
    ".vbs",
    ".js",
}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class UploadLimitError(ValueError):
    pass


class AsyncUpload(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes:
        ...


@dataclass(slots=True)
class UploadInfo:
    id: str
    filename: str
    mime_type: str
    size: int
    path: Path
    session_id: str


def validate_mime(filename: str, header_bytes: bytes) -> str:
    import mimetypes

    guessed, _ = mimetypes.guess_type(filename)
    mime = guessed or "application/octet-stream"

    if header_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif header_bytes[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif header_bytes[:4] == b"GIF8":
        mime = "image/gif"
    elif header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"WEBP":
        mime = "image/webp"
    elif header_bytes[:5] == b"%PDF-":
        mime = "application/pdf"

    allowed = any(mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES) or mime in ALLOWED_MIME_TYPES
    if not allowed:
        raise ValueError(f"MIME type '{mime}' is not allowed")

    ext = Path(filename).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValueError(f"File extension '{ext}' is blocked")

    return mime


def _safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if not (ext and all(ch.isalnum() or ch == "." for ch in ext)):
        return ""
    return ext


def _new_upload_destination(uploads_dir: Path, filename: str) -> tuple[str, Path]:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex[:8]
    destination = uploads_dir / f"{upload_id}{_safe_extension(filename)}"
    resolved_destination = destination.resolve()
    if resolved_destination.parent != uploads_dir.resolve():
        raise ValueError("Invalid upload path")
    return upload_id, destination


async def stage_upload_stream(
    upload: AsyncUpload,
    *,
    session_id: str,
    uploads_dir: Path,
    remaining_total_bytes: int,
) -> UploadInfo:
    filename = upload.filename or "untitled"
    upload_id, destination = _new_upload_destination(uploads_dir, filename)
    size = 0
    header = b""
    mime_type: str | None = None

    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break

                if mime_type is None:
                    header = chunk[:16]
                    mime_type = validate_mime(filename, header)

                next_size = size + len(chunk)
                if next_size > MAX_FILE_SIZE:
                    raise UploadLimitError(
                        f"File '{filename}' exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit"
                    )
                if next_size > remaining_total_bytes:
                    raise UploadLimitError(
                        f"Total upload size exceeds {MAX_TOTAL_SIZE // (1024 * 1024)} MB limit"
                    )

                handle.write(chunk)
                size = next_size

        if mime_type is None:
            mime_type = validate_mime(filename, header)

        return UploadInfo(
            id=upload_id,
            filename=filename,
            mime_type=mime_type,
            size=size,
            path=destination,
            session_id=session_id,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
