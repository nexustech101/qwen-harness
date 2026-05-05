from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from registers.db import db_field, dispose_all, DatabaseRegistry, HasMany

from api.config.config import get_settings

db = DatabaseRegistry()

settings = get_settings()
DATABASE_URL = settings.database_url


@db.database_registry(DATABASE_URL, table_name="chat_sessions", key_field="id")
class ChatSession(BaseModel):
    id: str
    title: str = "New chat"
    model: str = db_field(index=True)
    status: str = db_field(index=True, default="idle")
    created_at: str = db_field(index=True)
    updated_at: str


@db.database_registry(DATABASE_URL, table_name="chat_messages", key_field="id")
class ChatMessage(BaseModel):
    id: int | None = None
    session_id: str = db_field(index=True, foreign_key="chat_sessions.id")
    role: str
    content: str
    metadata: str | None = None  # JSON string
    created_at: str = db_field(index=True)


@db.database_registry(DATABASE_URL, table_name="workflows", key_field="id")
class Workflow(BaseModel):
    id: str
    name: str = db_field(index=True)
    description: str = ""
    definition: str = "{}"  # JSON: {"steps": [...], "triggers": [...]}
    enabled: bool = db_field(index=True, default=True)
    created_at: str = db_field(index=True)
    updated_at: str


@db.database_registry(DATABASE_URL, table_name="workflow_runs", key_field="id")
class WorkflowRun(BaseModel):
    id: str
    workflow_id: str = db_field(index=True, foreign_key="workflows.id")
    status: str = db_field(index=True, default="pending")  # pending | running | done | error
    result: str | None = None  # JSON string
    started_at: str = db_field(index=True)
    finished_at: str | None = None


# Relationships
ChatSession.messages = HasMany(ChatMessage, foreign_key="session_id")
Workflow.runs = HasMany(WorkflowRun, foreign_key="workflow_id")

ALL_MODELS = [ChatSession, ChatMessage, Workflow, WorkflowRun]


def initialize_database() -> None:
    for model in ALL_MODELS:
        if not model.schema_exists():
            model.create_schema()
        # Additive migrations: ensure columns exist
    ChatMessage.objects.ensure_column("metadata", str, nullable=True)
    WorkflowRun.objects.ensure_column("finished_at", str, nullable=True)


def dispose_database() -> None:
    dispose_all()

