"""Session, message, agent, upload, and file routes for runtime interactions."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import config
from api.modules.dependencies import get_current_user, get_optional_user, run_db
from api.modules.runtime_persistence import delete_persistent_session
from api.modules.uploads import (
    IMAGE_MIME_TYPES,
    MAX_FILES_PER_REQUEST,
    MAX_TOTAL_SIZE,
    UploadLimitError,
    stage_upload_stream,
)
from api.modules.session_manager import manager
from api.router.routes.runtime_common import (
    async_require_session,
    build_tree,
    current_user_id,
    session_to_response,
)
from api.schemas.agent import (
    AgentDetailResponse,
    AgentSummary,
    CreateSessionRequest,
    FileContentResponse,
    MessageResponse,
    PromptAccepted,
    SendPromptRequest,
    SessionResponse,
    UploadMeta,
    UploadResponse,
)
from api.schemas.conversation import (
    ConversationHistoryResponse,
    ConversationMessagePublic,
    ConversationSessionPublic,
    LlmUsageEventPublic,
)
from api.services.chat_service import get_conversation_history_for_user, list_chat_sessions_for_user

router = APIRouter(tags=["agent-runtime"])


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest, current_user=Depends(get_optional_user)):
    if req.chat_only or not req.project_root:
        root = (Path(config.WORKSPACE_HOME) / "chat-sessions").resolve()
        root.mkdir(parents=True, exist_ok=True)
        title = req.title or "New chat"
        chat_only = True
    else:
        root = Path(req.project_root).resolve()
        title = req.title
        chat_only = False

    if not root.is_dir():
        raise HTTPException(400, f"project_root does not exist: {req.project_root}")

    user_id = current_user_id(current_user)
    persistence_mode = "persistent" if user_id is not None else "guest"
    session = await run_db(
        manager.create,
        project_root=str(root),
        user_id=user_id,
        persistence_mode=persistence_mode,
        model=req.model,
        planner_model=req.planner_model,
        coder_model=req.coder_model,
        max_turns=req.max_turns,
        use_dispatch=req.use_dispatch,
        async_dispatch=req.async_dispatch,
        title=title,
        chat_only=chat_only,
    )
    return session_to_response(session)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(current_user=Depends(get_optional_user)):
    user_id = current_user_id(current_user)
    if user_id is not None:
        rows, _ = await run_db(list_chat_sessions_for_user, user_id, 200, 0)
        for row in rows:
            await run_db(manager.get, row.id, user_id=user_id)
    return [session_to_response(session) for session in manager.list_all(user_id=user_id)]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, current_user=Depends(get_optional_user)):
    return session_to_response(await async_require_session(session_id, current_user))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user=Depends(get_optional_user)):
    user_id = current_user_id(current_user)
    session = await run_db(manager.get, session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "Session not found")

    manager.forget(session_id)
    if session._task and not session._task.done():
        session._task.cancel()
        with suppress(asyncio.CancelledError):
            await session._task
    await run_db(session.cleanup_all_uploads)
    if session.is_persistent and user_id is not None:
        await run_db(delete_persistent_session, session_id, user_id)
    return {"status": "deleted"}


@router.post("/sessions/{session_id}/messages", response_model=PromptAccepted)
async def send_message(
    session_id: str,
    req: SendPromptRequest,
    current_user=Depends(get_optional_user),
):
    session = await async_require_session(session_id, current_user)
    if session.status == "running":
        raise HTTPException(409, "Session is already processing a prompt")

    prompt = req.prompt
    images: list[str] | None = None
    attachment_ids = req.attachments

    if attachment_ids:
        for attachment_id in attachment_ids:
            if not session.get_upload(attachment_id):
                raise HTTPException(400, f"Upload '{attachment_id}' not found or expired")
        prompt, image_paths = session.resolve_attachments(req.prompt, attachment_ids)
        images = image_paths or None

    async def _run_and_cleanup() -> None:
        try:
            await session.run_prompt(prompt, req.direct, images=images)
        finally:
            if attachment_ids:
                session.cleanup_uploads(attachment_ids)

    session._task = asyncio.create_task(_run_and_cleanup())
    return PromptAccepted(session_id=session_id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    return [
        MessageResponse(
            role=message["role"],
            content=message["content"],
            timestamp=message.get("timestamp"),
            metadata=message.get("metadata"),
        )
        for message in session.history
    ]


@router.get("/sessions/{session_id}/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(session_id: str, current_user=Depends(get_current_user)):
    history = await run_db(get_conversation_history_for_user, session_id, current_user.id)
    return ConversationHistoryResponse(
        session=ConversationSessionPublic.from_model(history["session"]),
        messages=[ConversationMessagePublic.from_model(item) for item in history["messages"]],
        usage_events=[LlmUsageEventPublic.from_model(item) for item in history["usage_events"]],
    )


@router.get("/sessions/{session_id}/agents", response_model=list[AgentSummary])
async def list_agents(session_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    return [
        AgentSummary(
            name=agent.name,
            status=agent.status,
            model=agent.model,
            turns_used=agent.turns_used,
            max_turns=agent.max_turns,
            goal=agent.goal,
        )
        for agent in session.agents.values()
    ]


@router.get("/sessions/{session_id}/agents/{agent_name}", response_model=AgentDetailResponse)
async def get_agent(session_id: str, agent_name: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    agent = session.agents.get(agent_name)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_name}' not found")

    live_messages = session.get_live_messages(agent_name)
    return AgentDetailResponse(
        name=agent.name,
        status=agent.status,
        model=agent.model,
        turns_used=agent.turns_used,
        max_turns=agent.max_turns,
        goal=agent.goal,
        messages=[MessageResponse(role=message["role"], content=message["content"]) for message in live_messages],
        tool_calls=agent.tool_calls,
        files_modified=agent.files_modified,
    )


@router.post("/sessions/{session_id}/agents/{agent_name}/prompt", response_model=PromptAccepted)
async def prompt_agent(
    session_id: str,
    agent_name: str,
    req: SendPromptRequest,
    current_user=Depends(get_optional_user),
):
    session = await async_require_session(session_id, current_user)
    if session.status == "running":
        raise HTTPException(409, "Session is already processing a prompt")

    prompt = req.prompt
    agent = session.agents.get(agent_name)
    if agent and agent_name != "main":
        prompt = (
            f"Continue the work of sub-agent '{agent_name}' (original goal: {agent.goal}). "
            f"New instruction: {req.prompt}"
        )

    session._task = asyncio.create_task(session.run_prompt(prompt, direct=True))
    return PromptAccepted(session_id=session_id)


@router.post("/sessions/{session_id}/uploads", response_model=UploadResponse, status_code=201)
async def upload_files(
    session_id: str,
    files: list[UploadFile],
    current_user=Depends(get_optional_user),
):
    session = await async_require_session(session_id, current_user)
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Too many files (max {MAX_FILES_PER_REQUEST})")

    total_size = 0
    uploads: list[UploadMeta] = []
    staged_ids: list[str] = []
    try:
        for upload in files:
            remaining_total = MAX_TOTAL_SIZE - total_size
            try:
                info = await stage_upload_stream(
                    upload,
                    session_id=session.id,
                    uploads_dir=session.uploads_dir,
                    remaining_total_bytes=remaining_total,
                )
            except UploadLimitError as exc:
                raise HTTPException(413, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

            session.add_upload(info)
            staged_ids.append(info.id)
            total_size += info.size

            base_url = f"/api/sessions/{session_id}/uploads/{info.id}"
            thumbnail_url = f"{base_url}/thumbnail" if info.mime_type in IMAGE_MIME_TYPES else None
            uploads.append(
                UploadMeta(
                    id=info.id,
                    filename=info.filename,
                    mime_type=info.mime_type,
                    size=info.size,
                    url=base_url,
                    thumbnail_url=thumbnail_url,
                )
            )
    except HTTPException:
        session.cleanup_uploads(staged_ids)
        raise
    return UploadResponse(uploads=uploads)


@router.get("/sessions/{session_id}/uploads/{upload_id}")
async def serve_upload(session_id: str, upload_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    info = session.get_upload(upload_id)
    if not info or not info.path.exists():
        raise HTTPException(404, "Upload not found")
    if info.path.is_symlink():
        raise HTTPException(403, "Symlinks not allowed")
    return FileResponse(path=str(info.path), media_type=info.mime_type, filename=info.filename)


@router.get("/sessions/{session_id}/uploads/{upload_id}/thumbnail")
async def serve_thumbnail(session_id: str, upload_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    info = session.get_upload(upload_id)
    if not info or not info.path.exists():
        raise HTTPException(404, "Upload not found")
    if info.mime_type not in IMAGE_MIME_TYPES:
        raise HTTPException(204)

    thumbnail_path = info.path.parent / f"{info.id}_thumb.png"
    if not thumbnail_path.exists():
        try:
            from PIL import Image

            with Image.open(info.path) as image:
                image.thumbnail((200, 200))
                image.save(thumbnail_path, "PNG")
        except Exception:
            raise HTTPException(500, "Failed to generate thumbnail")

    return FileResponse(path=str(thumbnail_path), media_type="image/png")


@router.delete("/sessions/{session_id}/uploads/{upload_id}")
async def delete_upload(session_id: str, upload_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    session.delete_upload(upload_id)
    return {"status": "deleted"}


@router.get("/sessions/{session_id}/files")
async def get_file_tree(session_id: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    root = Path(session.project_root)
    return await run_db(build_tree, root, root, 4)


@router.get("/sessions/{session_id}/files/{file_path:path}", response_model=FileContentResponse)
async def read_file(session_id: str, file_path: str, current_user=Depends(get_optional_user)):
    session = await async_require_session(session_id, current_user)
    root = Path(session.project_root).resolve()
    resolved = (root / file_path).resolve()

    if not resolved.is_relative_to(root):
        raise HTTPException(403, "Path outside project root")
    if not resolved.is_file():
        raise HTTPException(404, "File not found")

    try:
        content = await run_db(resolved.read_text, encoding="utf-8", errors="replace")
        file_stat = await run_db(resolved.stat)
        return FileContentResponse(
            path=file_path,
            content=content,
            size=file_stat.st_size,
            lines=content.count("\n") + 1,
        )
    except Exception as exc:
        raise HTTPException(500, f"Failed to read file: {exc}")
