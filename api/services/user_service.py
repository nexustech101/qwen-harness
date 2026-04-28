from __future__ import annotations

from api.config.security import utc_now_iso
from api.db.models import User
from api.schemas.user import UserUpdate


def _now() -> str:
    return utc_now_iso()


def create_user(
    email: str,
    full_name: str,
    password: str,
    is_admin: bool = False,
    firebase_uid: str | None = None,
) -> User:
    now = _now()
    return User.objects.create(
        email=email,
        full_name=full_name,
        password=password,
        firebase_uid=firebase_uid,
        is_active=True,
        is_admin=is_admin,
        created_at=now,
        updated_at=now,
    )


def get_user_by_id(user_id: int) -> User:
    return User.objects.require(user_id)


def get_user_by_email(email: str) -> User:
    return User.objects.require(email=email)


def update_user(user_id: int, payload: UserUpdate, is_admin_actor: bool) -> User:
    user = get_user_by_id(user_id)

    if payload.full_name is not None:
        user.full_name = payload.full_name

    if payload.is_active is not None:
        if not is_admin_actor:
            raise PermissionError("Only admins can update account activation status")
        user.is_active = payload.is_active

    if payload.is_admin is not None:
        if not is_admin_actor:
            raise PermissionError("Only admins can change admin role")
        user.is_admin = payload.is_admin

    user.updated_at = _now()
    user.save()
    return user


def deactivate_user(user_id: int) -> User:
    user = get_user_by_id(user_id)
    user.is_active = False
    user.updated_at = _now()
    user.save()
    return user


def list_users(limit: int, offset: int, is_active: bool | None = None) -> tuple[list[User], int]:
    filters: dict[str, object] = {}
    if is_active is not None:
        filters["is_active"] = is_active

    rows = User.objects.filter(order_by="-id", limit=limit, offset=offset, **filters)
    total = User.objects.count(**filters)
    return rows, total


def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    user = get_user_by_id(user_id)
    if not user.verify_password(current_password):
        return False
    user.password = new_password
    user.updated_at = _now()
    user.save()
    return True

