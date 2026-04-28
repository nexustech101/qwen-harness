from __future__ import annotations

import json
from typing import Any

import registers.cli as cli

from cli.bootstrap import bootstrap
from api.schemas import UserUpdate
from api.services.user_service import create_user, get_user_by_id, list_users, update_user
from api.services.auth_service import revoke_all_user_sessions


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


@cli.register(name="create-user", description="Create a user account")
@cli.argument("email", type=str, help="User email")
@cli.argument("password", type=str, help="Plain text password")
@cli.argument("full_name", type=str, default="", help="Display name")
@cli.argument("is_admin", type=bool, default=False, help="Grant admin privileges")
@cli.option("--create-user")
def create_user_command(email: str, password: str, full_name: str = "", is_admin: bool = False) -> str:
    bootstrap()
    name = full_name or email.split("@", maxsplit=1)[0]
    user = create_user(email=email, full_name=name, password=password, is_admin=is_admin)
    return _to_json(
        {
            "action": "create-user",
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        }
    )


@cli.register(name="list-users", description="List user accounts")
@cli.argument("limit", type=int, default=25, help="Page size")
@cli.argument("offset", type=int, default=0, help="Offset")
@cli.argument("is_active", type=str, default="all", help="Filter: all|true|false")
@cli.option("--list-users")
def list_users_command(limit: int = 25, offset: int = 0, is_active: str = "all") -> str:
    bootstrap()
    filter_value: bool | None
    normalized = is_active.strip().lower()
    if normalized in {"all", ""}:
        filter_value = None
    elif normalized in {"true", "1", "yes"}:
        filter_value = True
    elif normalized in {"false", "0", "no"}:
        filter_value = False
    else:
        return _to_json(
            {
                "action": "list-users",
                "error": "invalid_filter",
                "detail": "is_active must be one of: all, true, false",
            }
        )

    users, total = list_users(limit=limit, offset=offset, is_active=filter_value)
    return _to_json(
        {
            "action": "list-users",
            "total": total,
            "items": [
                {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "is_admin": user.is_admin,
                    "is_active": user.is_active,
                }
                for user in users
            ],
        }
    )


@cli.register(name="set-password", description="Set a new password for a user")
@cli.argument("user_id", type=int, help="User ID")
@cli.argument("new_password", type=str, help="New plain-text password")
@cli.option("--set-password")
def set_password_command(user_id: int, new_password: str) -> str:
    bootstrap()
    user = get_user_by_id(user_id)
    user.password = new_password
    user.save()
    return _to_json({"action": "set-password", "user_id": user.id, "success": True})


@cli.register(name="deactivate-user", description="Deactivate a user account")
@cli.argument("user_id", type=int, help="User ID")
@cli.option("--deactivate-user")
def deactivate_user_command(user_id: int) -> str:
    bootstrap()
    user = update_user(user_id, UserUpdate(is_active=False), is_admin_actor=True)
    revoked = revoke_all_user_sessions(user_id)
    return _to_json(
        {
            "action": "deactivate-user",
            "user_id": user.id,
            "is_active": user.is_active,
            "revoked_sessions": revoked,
        }
    )


@cli.register(name="activate-user", description="Activate a user account")
@cli.argument("user_id", type=int, help="User ID")
@cli.option("--activate-user")
def activate_user_command(user_id: int) -> str:
    bootstrap()
    user = update_user(user_id, UserUpdate(is_active=True), is_admin_actor=True)
    return _to_json({"action": "activate-user", "user_id": user.id, "is_active": user.is_active})


@cli.register(name="promote-admin", description="Promote a user to admin")
@cli.argument("user_id", type=int, help="User ID")
@cli.option("--promote-admin")
def promote_admin_command(user_id: int) -> str:
    bootstrap()
    user = update_user(user_id, UserUpdate(is_admin=True), is_admin_actor=True)
    return _to_json({"action": "promote-admin", "user_id": user.id, "is_admin": user.is_admin})

