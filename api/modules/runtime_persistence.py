from __future__ import annotations

from typing import Any

from api.services.chat_service import (
    append_chat_message,
    delete_chat_session_for_user,
    get_chat_session_for_user,
    list_chat_messages_for_user,
    record_usage_event,
    set_chat_session_status,
    upsert_chat_session,
)


def persist_session(session: Any) -> None:
    if not session.is_persistent:
        return
    upsert_chat_session(
        session_id=session.id,
        user_id=int(session.user_id),
        project_root=session.project_root,
        project_name=session.title or session.project_name,
        workspace_key=session.workspace_key,
        workspace_root=session.workspace_root,
        model=session.model,
        status=session.status,
    )


def persist_message(
    *,
    session_id: str,
    user_id: int,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    agent_name: str | None = None,
) -> None:
    append_chat_message(session_id, user_id, role, content, metadata, agent_name)


def persist_status(*, session_id: str, user_id: int, status: str) -> None:
    set_chat_session_status(session_id, user_id, status)


def persist_usage_event(
    *,
    event_type: str,
    session_id: str,
    user_id: int,
    payload: dict[str, Any] | None = None,
) -> None:
    record_usage_event(event_type=event_type, session_id=session_id, user_id=user_id, payload=payload)


def load_session_record(session_id: str, user_id: int):
    return get_chat_session_for_user(session_id, user_id)


def load_message_history(session_id: str, user_id: int):
    return list_chat_messages_for_user(session_id, user_id)


def delete_persistent_session(session_id: str, user_id: int) -> bool:
    return delete_chat_session_for_user(session_id, user_id)
