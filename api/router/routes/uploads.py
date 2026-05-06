"""Upload routes — stage, serve, and delete file uploads attached to a chat session."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.modules.session_manager import manager
from api.modules.uploads import (
    MAX_FILES_PER_REQUEST,
    MAX_TOTAL_SIZE,
    UploadLimitError,
    stage_upload_stream,
)

router = APIRouter(tags=["uploads"])

_UPLOADS_BASE = Path(tempfile.gettempdir()) / "agent_uploads"


def _require_session(session_id: str):
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


# ── Stage uploads ──────────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/uploads")
async def stage_uploads(
    session_id: str,
    files: Annotated[list[UploadFile], File()],
) -> dict[str, Any]:
    session = _require_session(session_id)

    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Maximum {MAX_FILES_PER_REQUEST} files per request")

    uploads_dir = _UPLOADS_BASE / session_id
    remaining = MAX_TOTAL_SIZE
    results = []

    for f in files:
        try:
            info = await stage_upload_stream(
                f,
                session_id=session_id,
                uploads_dir=uploads_dir,
                remaining_total_bytes=remaining,
            )
            session.add_upload(info)
            remaining -= info.size
            is_image = info.mime_type.startswith("image/")
            results.append({
                "id": info.id,
                "filename": info.filename,
                "mime_type": info.mime_type,
                "size": info.size,
                "url": f"/api/sessions/{session_id}/uploads/{info.id}",
                "thumbnail_url": (
                    f"/api/sessions/{session_id}/uploads/{info.id}/thumbnail"
                    if is_image
                    else None
                ),
            })
        except UploadLimitError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return {"uploads": results}


# ── Serve uploaded file ────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/uploads/{upload_id}")
async def serve_upload(session_id: str, upload_id: str) -> FileResponse:
    session = _require_session(session_id)
    info = session.get_upload(upload_id)
    if info is None or not info.path.exists():
        raise HTTPException(404, "Upload not found")
    return FileResponse(
        path=str(info.path),
        media_type=info.mime_type,
        filename=info.filename,
    )


# ── Serve thumbnail (images only) ─────────────────────────────────────────────

@router.get("/sessions/{session_id}/uploads/{upload_id}/thumbnail")
async def serve_thumbnail(session_id: str, upload_id: str) -> FileResponse:
    session = _require_session(session_id)
    info = session.get_upload(upload_id)
    if info is None or not info.path.exists():
        raise HTTPException(404, "Upload not found")
    if not info.mime_type.startswith("image/"):
        raise HTTPException(404, "No thumbnail for non-image files")
    return FileResponse(path=str(info.path), media_type=info.mime_type)


# ── Delete upload ──────────────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}/uploads/{upload_id}", status_code=204)
async def delete_upload(session_id: str, upload_id: str) -> None:
    session = _require_session(session_id)
    session.delete_upload(upload_id)
