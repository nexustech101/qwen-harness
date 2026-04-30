from __future__ import annotations

from typing import Any

from registers.db import RecordNotFoundError

from api.config.security import utc_now_iso
from api.db.models import ChatMessage, ChatSession, LLMUsageEvent


def _now() -> str:
    return utc_now_iso()


def upsert_chat_session(
    session_id: str,
    user_id: int,
    project_root: str,
    project_name: str | None,
    workspace_key: str | None,
    workspace_root: str | None,
    model: str,
    status: str = "idle",
) -> ChatSession:
    now = _now()
    try:
        session = ChatSession.objects.require(id=session_id)
        if session.user_id != user_id:
            raise PermissionError("Chat session does not belong to this user")
        session.project_root = project_root
        session.project_name = project_name
        session.workspace_key = workspace_key
        session.workspace_root = workspace_root
        session.model = model
        session.status = status
        session.updated_at = now
        session.last_activity_at = now
        session.save()
        return session
    except RecordNotFoundError:
        return ChatSession.objects.create(
            id=session_id,
            user_id=user_id,
            project_root=project_root,
            project_name=project_name,
            workspace_key=workspace_key,
            workspace_root=workspace_root,
            model=model,
            status=status,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
        )


def get_chat_session_for_user(session_id: str, user_id: int) -> ChatSession:
    session = ChatSession.objects.require(id=session_id)
    if session.user_id != user_id:
        raise PermissionError("Chat session access denied")
    return session


def list_chat_sessions_for_user(user_id: int, limit: int = 25, offset: int = 0) -> tuple[list[ChatSession], int]:
    rows = ChatSession.objects.filter(
        user_id=user_id,
        order_by="-last_activity_at",
        limit=limit,
        offset=offset,
    )
    total = ChatSession.objects.count(user_id=user_id)
    return rows, total


def append_chat_message(
    session_id: str,
    user_id: int,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    agent_name: str | None = None,
) -> ChatMessage:
    session = get_chat_session_for_user(session_id, user_id)
    now = _now()
    msg = ChatMessage.objects.create(
        session_id=session.id,
        user_id=user_id,
        role=role,
        content=content,
        agent_name=agent_name,
        metadata=metadata or None,
        created_at=now,
    )
    session.last_activity_at = now
    session.updated_at = now
    session.save()
    record_usage_event(
        event_type="conversation.message_created",
        session_id=session.id,
        user_id=user_id,
        payload={
            "message_id": msg.id,
            "role": role,
            "agent_name": agent_name,
            "content_length": len(content),
            "metadata": metadata or {},
        },
    )
    return msg


def list_chat_messages_for_user(session_id: str, user_id: int) -> list[ChatMessage]:
    _ = get_chat_session_for_user(session_id, user_id)
    return ChatMessage.objects.filter(session_id=session_id, order_by="id")


def delete_chat_session_for_user(session_id: str, user_id: int) -> bool:
    _ = get_chat_session_for_user(session_id, user_id)
    ChatMessage.objects.delete_where(session_id=session_id)
    ChatSession.objects.delete(session_id)
    return True


def set_chat_session_status(session_id: str, user_id: int, status: str) -> ChatSession:
    session = get_chat_session_for_user(session_id, user_id)
    now = _now()
    session.status = status
    session.updated_at = now
    session.last_activity_at = now
    session.save()
    return session


def record_usage_event(
    event_type: str,
    session_id: str | None = None,
    user_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> LLMUsageEvent:
    return LLMUsageEvent.objects.create(
        session_id=session_id,
        user_id=user_id,
        event_type=event_type,
        payload=payload or None,
        created_at=_now(),
    )


def list_usage_events_for_session(session_id: str, user_id: int | None = None) -> list[LLMUsageEvent]:
    filters: dict[str, Any] = {"session_id": session_id}
    if user_id is not None:
        filters["user_id"] = user_id
    return LLMUsageEvent.objects.filter(order_by="id", **filters)


def get_conversation_history_for_user(session_id: str, user_id: int) -> dict[str, Any]:
    session = get_chat_session_for_user(session_id, user_id)
    return {
        "session": session,
        "messages": list_chat_messages_for_user(session_id, user_id),
        "usage_events": list_usage_events_for_session(session_id, user_id),
    }


def list_conversation_histories(
    *,
    limit: int,
    offset: int,
    user_id: int | None = None,
    session_id: str | None = None,
    status: str | None = None,
    model: str | None = None,
    project_name: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    filters: dict[str, Any] = {}
    if user_id is not None:
        filters["user_id"] = user_id
    if session_id:
        filters["id"] = session_id
    if status:
        filters["status"] = status
    if model:
        filters["model"] = model
    if project_name:
        filters["project_name"] = project_name
    if created_after:
        filters["created_at__gte"] = created_after
    if created_before:
        filters["created_at__lte"] = created_before

    sessions = ChatSession.objects.filter(order_by="-last_activity_at", limit=limit, offset=offset, **filters)
    total = ChatSession.objects.count(**filters)
    histories = [
        {
            "session": session,
            "messages": ChatMessage.objects.filter(session_id=session.id, order_by="id"),
            "usage_events": list_usage_events_for_session(session.id, session.user_id),
        }
        for session in sessions
    ]
    return histories, total
