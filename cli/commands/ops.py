from __future__ import annotations

import json
from typing import Any

import registers.cli as cli

from cli.bootstrap import bootstrap
from api.services.ops_service import get_schema_metadata, list_auth_events


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


@cli.register(name="schema-meta", description="Show migration and schema metadata")
@cli.option("--schema-meta")
def schema_meta_command() -> str:
    bootstrap()
    metadata = get_schema_metadata()
    return _to_json(
        {
            "action": "schema-meta",
            "current_schema_version": metadata["current_schema_version"],
            "applied_count": metadata["applied_count"],
            "migrations": [
                {
                    "version": migration.version,
                    "name": migration.name,
                    "applied_at": migration.applied_at,
                    "details": migration.details,
                }
                for migration in metadata["migrations"]
            ],
        }
    )


@cli.register(name="audit-events", description="Query auth audit events")
@cli.argument("limit", type=int, default=25, help="Page size")
@cli.argument("offset", type=int, default=0, help="Offset")
@cli.argument("action", type=str, default="", help="Action filter")
@cli.argument("email", type=str, default="", help="Email filter")
@cli.argument("success", type=str, default="all", help="Filter: all|true|false")
@cli.option("--audit-events")
def audit_events_command(
    limit: int = 25,
    offset: int = 0,
    action: str = "",
    email: str = "",
    success: str = "all",
) -> str:
    bootstrap()
    success_filter: bool | None
    success_normalized = success.strip().lower()
    if success_normalized in {"all", ""}:
        success_filter = None
    elif success_normalized in {"true", "1", "yes"}:
        success_filter = True
    elif success_normalized in {"false", "0", "no"}:
        success_filter = False
    else:
        return _to_json(
            {
                "action": "audit-events",
                "error": "invalid_filter",
                "detail": "success must be one of: all, true, false",
            }
        )

    rows, total = list_auth_events(
        limit=limit,
        offset=offset,
        action=action.strip() or None,
        email=email.strip() or None,
        success=success_filter,
    )
    return _to_json(
        {
            "action": "audit-events",
            "total": total,
            "items": [
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "email": row.email,
                    "ip_address": row.ip_address,
                    "user_agent": row.user_agent,
                    "request_id": row.request_id,
                    "action": row.action,
                    "success": row.success,
                    "details": row.details,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        }
    )

