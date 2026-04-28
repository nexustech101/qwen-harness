from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from registers.db import RecordNotFoundError

from api.config.config import get_settings
from api.config.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    parse_iso_datetime,
    utc_now_iso,
)
from api.db.models import AuthEvent, RefreshSession, User
from api.integrations.firebase import verify_firebase_token
from api.services.user_service import create_user, get_user_by_email, get_user_by_id

logger = logging.getLogger("user_api.services.auth")


def _now() -> str:
    return utc_now_iso()


def _is_expired(iso_value: str) -> bool:
    expires_at = parse_iso_datetime(iso_value)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


def authenticate_user(email: str, password: str) -> User | None:
    try:
        user = get_user_by_email(email)
    except RecordNotFoundError:
        return None

    if not user.is_active:
        return None
    if not user.verify_password(password):
        return None

    user.last_login_at = _now()
    user.updated_at = _now()
    user.save()
    return user


def issue_tokens_for_user(user: User) -> dict[str, str | int]:
    if user.id is None:
        raise ValueError("Cannot issue tokens for a user without an ID")

    settings = get_settings()
    access_token, expires_in = create_access_token(user.id, user.email, settings)
    refresh_token, jti, refresh_expires_at = create_refresh_token(user.id, settings)
    RefreshSession.objects.create(
        user_id=user.id,
        token_jti=jti,
        expires_at=refresh_expires_at,
        created_at=_now(),
        revoked_at=None,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


def rotate_refresh_token(refresh_token: str) -> dict[str, str | int]:
    settings = get_settings()
    payload = decode_token(refresh_token, expected_type="refresh", settings=settings)
    token_jti = payload.get("jti")
    try:
        user_id = int(payload.get("sub", "0"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if not token_jti or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        session = RefreshSession.objects.require(token_jti=token_jti)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if _is_expired(session.expires_at):
        session.revoked_at = _now()
        session.save()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = get_user_by_id(user_id)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    session.revoked_at = _now()
    session.save()
    return issue_tokens_for_user(user)


def revoke_refresh_token(refresh_token: str) -> None:
    settings = get_settings()
    payload = decode_token(refresh_token, expected_type="refresh", settings=settings)
    token_jti = payload.get("jti")
    if not token_jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        session = RefreshSession.objects.require(token_jti=token_jti)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.save()


def revoke_session_by_jti(token_jti: str) -> bool:
    try:
        session = RefreshSession.objects.require(token_jti=token_jti)
    except RecordNotFoundError:
        return False

    if session.revoked_at is None:
        session.revoked_at = _now()
        session.save()
    return True


def revoke_all_user_sessions(user_id: int) -> int:
    sessions = RefreshSession.objects.filter(user_id=user_id, revoked_at__is_null=True)
    revoked = 0
    for session in sessions:
        session.revoked_at = _now()
        session.save()
        revoked += 1
    return revoked


def exchange_firebase_token(id_token: str, create_if_missing: bool) -> tuple[User, dict[str, str | int]]:
    settings = get_settings()
    claims = verify_firebase_token(id_token, settings)

    firebase_uid = claims.get("uid") or claims.get("sub")
    email = claims.get("email")
    name = claims.get("name") or ""
    email_verified = claims.get("email_verified", False)

    if not firebase_uid or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase token missing required identity claims",
        )
    if settings.firebase_require_verified_email and not email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase email is not verified",
        )

    user: User | None = None
    try:
        user = User.objects.require(firebase_uid=firebase_uid)
    except RecordNotFoundError:
        pass

    if user is None:
        try:
            user = User.objects.require(email=email)
            if not user.firebase_uid:
                user.firebase_uid = firebase_uid
                user.updated_at = _now()
                user.save()
        except RecordNotFoundError:
            if not create_if_missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No local account mapped to this Firebase identity",
                ) from None
            generated_password = secrets.token_urlsafe(32)
            full_name = name.strip() or email.split("@", maxsplit=1)[0]
            user = create_user(
                email=email,
                full_name=full_name,
                password=generated_password,
                is_admin=False,
                firebase_uid=firebase_uid,
            )
            logger.info(
                "firebase_user_provisioned",
                extra={"event": "firebase_user_provisioned", "email": email, "user_id": user.id},
            )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    user.last_login_at = _now()
    user.updated_at = _now()
    user.save()
    return user, issue_tokens_for_user(user)


def record_auth_event(
    user_id: int | None,
    email: str,
    ip_address: str | None,
    action: str,
    success: bool,
    user_agent: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuthEvent:
    detail_payload: str | None = None
    if details is not None:
        detail_payload = json.dumps(details, ensure_ascii=True, sort_keys=True)

    logger.info(
        "auth_event",
        extra={
            "event": "auth_event",
            "user_id": user_id,
            "email": email,
            "action": action,
            "success": success,
            "details": details or {},
        },
    )
    return AuthEvent.objects.create(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        action=action,
        success=success,
        details=detail_payload,
        created_at=_now(),
    )
