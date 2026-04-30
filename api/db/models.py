from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from pydantic import BaseModel, EmailStr, Field
from registers.db import db_field, dispose_all, DatabaseRegistry
from sqlalchemy import text

from api.config.config import get_settings
from api.config.security import utc_now_iso

db = DatabaseRegistry()

settings = get_settings()
USER_DATABASE_URL = settings.database_url


@db.database_registry(
    USER_DATABASE_URL,
    table_name="users",
    key_field="id",
    unique_fields=["email"],
)
class User(BaseModel):
    id: int | None = None
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)
    firebase_uid: str | None = db_field(index=True, unique=True, default=None)
    is_active: bool = True
    is_admin: bool = False
    created_at: str
    updated_at: str
    last_login_at: str | None = None


@db.database_registry(
    USER_DATABASE_URL,
    table_name="refresh_sessions",
    key_field="id",
    unique_fields=["token_jti"],
)
class RefreshSession(BaseModel):
    id: int | None = None
    user_id: int = db_field(index=True, foreign_key="users.id")
    token_jti: str = db_field(index=True, unique=True)
    expires_at: str
    created_at: str
    revoked_at: str | None = None


@db.database_registry(USER_DATABASE_URL, table_name="auth_events", key_field="id")
class AuthEvent(BaseModel):
    id: int | None = None
    user_id: int | None = db_field(index=True, foreign_key="users.id", default=None)
    email: str = db_field(index=True)
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = db_field(index=True, default=None)
    action: str = db_field(index=True)
    success: bool = db_field(index=True)
    details: str | None = None
    created_at: str = db_field(index=True)


@db.database_registry(
    USER_DATABASE_URL,
    table_name="billing_accounts",
    key_field="id",
    unique_fields=["user_id", "stripe_customer_id"],
)
class BillingAccount(BaseModel):
    id: int | None = None
    user_id: int = db_field(index=True, foreign_key="users.id", unique=True)
    stripe_customer_id: str = db_field(index=True, unique=True)
    stripe_subscription_id: str | None = db_field(index=True, unique=True, default=None)
    subscription_status: str | None = db_field(index=True, default=None)
    price_id: str | None = db_field(index=True, default=None)
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
    created_at: str
    updated_at: str


@db.database_registry(
    USER_DATABASE_URL,
    table_name="schema_migrations",
    key_field="id",
    unique_fields=["version"],
)
class SchemaMigration(BaseModel):
    id: int | None = None
    version: int = db_field(index=True, unique=True)
    name: str
    applied_at: str
    details: str | None = None


@db.database_registry(
    USER_DATABASE_URL,
    table_name="chat_sessions",
    key_field="id",
)
class ChatSession(BaseModel):
    id: str
    user_id: int = db_field(index=True, foreign_key="users.id")
    project_root: str
    project_name: str | None = db_field(index=True, default=None)
    workspace_key: str | None = db_field(index=True, default=None)
    workspace_root: str | None = None
    model: str = db_field(index=True)
    status: str = db_field(index=True, default="idle")
    created_at: str = db_field(index=True)
    updated_at: str
    last_activity_at: str = db_field(index=True)


@db.database_registry(
    USER_DATABASE_URL,
    table_name="chat_messages",
    key_field="id",
)
class ChatMessage(BaseModel):
    id: int | None = None
    session_id: str = db_field(index=True, foreign_key="chat_sessions.id")
    user_id: int | None = db_field(index=True, foreign_key="users.id", default=None)
    role: str
    content: str
    agent_name: str | None = None
    metadata: dict[str, Any] | None = db_field(default=None)
    created_at: str


@db.database_registry(
    USER_DATABASE_URL,
    table_name="llm_usage_events",
    key_field="id",
)
class LLMUsageEvent(BaseModel):
    id: int | None = None
    session_id: str | None = db_field(index=True, foreign_key="chat_sessions.id", default=None)
    user_id: int | None = db_field(index=True, foreign_key="users.id", default=None)
    event_type: str = db_field(index=True)
    payload: dict[str, Any] | None = db_field(default=None)
    created_at: str


ALL_MODELS = [
    User,
    RefreshSession,
    AuthEvent,
    BillingAccount,
    SchemaMigration,
    ChatSession,
    ChatMessage,
    LLMUsageEvent,
]


def _migration_1() -> None:
    return


def _migration_2() -> None:
    RefreshSession.objects.ensure_column("revoked_at", str, nullable=True)


def _migration_3() -> None:
    User.objects.ensure_column("firebase_uid", str, nullable=True)


def _migration_4() -> None:
    AuthEvent.objects.ensure_column("user_agent", str, nullable=True)
    AuthEvent.objects.ensure_column("request_id", str, nullable=True)
    AuthEvent.objects.ensure_column("details", str, nullable=True)


def _migration_5() -> None:
    return


def _migration_6() -> None:
    return


def _ensure_index(model: type[BaseModel], table_name: str, column_name: str) -> None:
    index_name = f"idx_{table_name}_{column_name}"
    with model.objects.transaction() as conn:  # type: ignore[attr-defined]
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"))


def _json_or_none(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _update_json_column(model: type[BaseModel], row_id: int, column_name: str, value: dict[str, Any]) -> None:
    table = model.objects._table  # type: ignore[attr-defined]
    with model.objects.transaction() as conn:  # type: ignore[attr-defined]
        conn.execute(
            table.update()
            .where(table.c.id == row_id)
            .values({column_name: value})
        )


def _migration_7() -> None:
    for column in ("action", "success", "created_at"):
        _ensure_index(AuthEvent, "auth_events", column)

    for column in ("project_name", "model", "status", "created_at", "last_activity_at"):
        _ensure_index(ChatSession, "chat_sessions", column)

    ChatMessage.objects.ensure_column("metadata", dict, nullable=True)
    LLMUsageEvent.objects.ensure_column("payload", dict, nullable=True)

    if "metadata_json" in ChatMessage.objects.column_names():
        with ChatMessage.objects.transaction() as conn:
            rows = conn.execute(text("SELECT id, metadata_json FROM chat_messages WHERE metadata_json IS NOT NULL")).mappings().all()
        for row in rows:
            metadata = _json_or_none(row["metadata_json"])
            if metadata is not None:
                _update_json_column(ChatMessage, row["id"], "metadata", metadata)

    if "payload_json" in LLMUsageEvent.objects.column_names():
        with LLMUsageEvent.objects.transaction() as conn:
            rows = conn.execute(text("SELECT id, payload_json FROM llm_usage_events WHERE payload_json IS NOT NULL")).mappings().all()
        for row in rows:
            payload = _json_or_none(row["payload_json"])
            if payload is not None:
                _update_json_column(LLMUsageEvent, row["id"], "payload", payload)


MIGRATIONS: list[tuple[int, str, Callable[[], None]]] = [
    (1, "baseline_schema", _migration_1),
    (2, "refresh_session_revocation_column", _migration_2),
    (3, "firebase_identity_column", _migration_3),
    (4, "auth_event_observability_columns", _migration_4),
    (5, "billing_accounts_domain", _migration_5),
    (6, "chat_persistence_domain", _migration_6),
    (7, "analytics_indexes_and_structured_conversation_payloads", _migration_7),
]


def _apply_migrations() -> None:
    for version, name, migration in MIGRATIONS:
        already_applied = SchemaMigration.objects.exists(version=version)
        if already_applied:
            continue

        migration()
        SchemaMigration.objects.create(
            version=version,
            name=name,
            applied_at=utc_now_iso(),
            details=f"Applied migration {version}: {name}",
        )


def initialize_database() -> None:
    for model in ALL_MODELS:
        if not model.schema_exists():
            model.create_schema()

    _apply_migrations()


def dispose_database() -> None:
    dispose_all()
