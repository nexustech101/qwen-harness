from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.db.models import ChatMessage, ChatSession


class ConversationSessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    project_root: str
    project_name: str | None = None
    workspace_key: str | None = None
    workspace_root: str | None = None
    model: str
    status: str
    created_at: str
    updated_at: str
    last_activity_at: str

    @classmethod
    def from_model(cls, session: ChatSession) -> "ConversationSessionPublic":
        return cls.model_validate(session)


class ConversationMessagePublic(BaseModel):
    id: int
    session_id: str
    user_id: int | None = None
    role: str
    content: str
    agent_name: str | None = None
    metadata: dict[str, Any] | None = None
    content_length: int
    created_at: str

    @classmethod
    def from_model(cls, message: ChatMessage) -> "ConversationMessagePublic":
        return cls(
            id=message.id or 0,
            session_id=message.session_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            agent_name=message.agent_name,
            metadata=message.metadata,
            content_length=len(message.content),
            created_at=message.created_at,
        )


class LLMUsageEventPublic(BaseModel):
    id: int
    session_id: str | None = None
    user_id: int | None = None
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: str


class ConversationHistoryResponse(BaseModel):
    session: ConversationSessionPublic
    messages: list[ConversationMessagePublic] = Field(default_factory=list)
    usage_events: list[LLMUsageEventPublic] = Field(default_factory=list)


class ConversationHistoryPage(BaseModel):
    items: list[ConversationHistoryResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
