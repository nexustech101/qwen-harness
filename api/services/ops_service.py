from __future__ import annotations

from typing import Any

from api.db.models import AuthEvent, SchemaMigration


def list_auth_events(
    *,
    limit: int,
    offset: int,
    action: str | None = None,
    email: str | None = None,
    success: bool | None = None,
    user_id: int | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> tuple[list[AuthEvent], int]:
    filters: dict[str, Any] = {}
    if action:
        filters["action"] = action
    if email:
        filters["email"] = email
    if success is not None:
        filters["success"] = success
    if user_id is not None:
        filters["user_id"] = user_id
    if created_after:
        filters["created_at__gte"] = created_after
    if created_before:
        filters["created_at__lte"] = created_before

    rows = AuthEvent.objects.filter(order_by="-id", limit=limit, offset=offset, **filters)
    total = AuthEvent.objects.count(**filters)
    return rows, total


def get_schema_migrations() -> list[SchemaMigration]:
    return SchemaMigration.objects.filter(order_by="version")


def get_schema_metadata() -> dict[str, Any]:
    migrations = get_schema_migrations()
    latest_version = migrations[-1].version if migrations else 0
    return {
        "current_schema_version": latest_version,
        "applied_count": len(migrations),
        "migrations": migrations,
    }

