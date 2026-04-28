from fastapi import APIRouter, Depends, Query, Request

from api.modules.dependencies import get_admin_user, run_db
from api.config.config import get_settings
from api.schemas import (
    AuthEventPage,
    AuthEventPublic,
    ConversationHistoryPage,
    ConversationHistoryResponse,
    ConversationMessagePublic,
    ConversationSessionPublic,
    LlmUsageEventPublic,
    MigrationMetadataResponse,
    MigrationRecord,
    VersionMetadataResponse,
)
from api.services.chat_service import list_conversation_histories
from api.services.ops_service import get_schema_metadata, list_auth_events

router = APIRouter(prefix="/ops", tags=["ops"])
settings = get_settings()


@router.get("/audit-events", response_model=AuthEventPage)
async def audit_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    email: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    user_id: int | None = Query(default=None),
    created_after: str | None = Query(default=None),
    created_before: str | None = Query(default=None),
    current_user=Depends(get_admin_user),
):
    del request, current_user
    rows, total = await run_db(
        list_auth_events,
        limit=limit,
        offset=offset,
        action=action,
        email=email,
        success=success,
        user_id=user_id,
        created_after=created_after,
        created_before=created_before,
    )
    return AuthEventPage(
        items=[AuthEventPublic.from_model(item) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversation-history", response_model=ConversationHistoryPage)
async def conversation_history_export(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None),
    session_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    model: str | None = Query(default=None),
    project_name: str | None = Query(default=None),
    created_after: str | None = Query(default=None),
    created_before: str | None = Query(default=None),
    current_user=Depends(get_admin_user),
):
    del request, current_user
    rows, total = await run_db(
        list_conversation_histories,
        limit=limit,
        offset=offset,
        user_id=user_id,
        session_id=session_id,
        status=status,
        model=model,
        project_name=project_name,
        created_after=created_after,
        created_before=created_before,
    )
    return ConversationHistoryPage(
        items=[
            ConversationHistoryResponse(
                session=ConversationSessionPublic.from_model(item["session"]),
                messages=[ConversationMessagePublic.from_model(message) for message in item["messages"]],
                usage_events=[LlmUsageEventPublic.from_model(event) for event in item["usage_events"]],
            )
            for item in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/meta/migrations", response_model=MigrationMetadataResponse)
async def migration_metadata(current_user=Depends(get_admin_user)):
    del current_user
    metadata = await run_db(get_schema_metadata)
    migrations = [MigrationRecord.from_model(row) for row in metadata["migrations"]]
    return MigrationMetadataResponse(
        current_schema_version=metadata["current_schema_version"],
        applied_count=metadata["applied_count"],
        migrations=migrations,
    )


@router.get("/meta/version", response_model=VersionMetadataResponse)
async def version_metadata(current_user=Depends(get_admin_user)):
    del current_user
    metadata = await run_db(get_schema_metadata)
    return VersionMetadataResponse(
        app_name=settings.app_name,
        api_version=settings.api_version,
        current_schema_version=metadata["current_schema_version"],
        database_url=settings.database_url,
        migration_count=metadata["applied_count"],
    )
