from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from .config import Settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def create_access_token(user_id: int, email: str, settings: Settings) -> tuple[str, int]:
    now = utc_now()
    expires_delta = timedelta(minutes=settings.access_token_minutes)
    expires_at = now + expires_delta
    claims = {
        "sub": str(user_id),
        "email": email,
        "token_type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_id: int, settings: Settings) -> tuple[str, str, str]:
    now = utc_now()
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.refresh_token_days)
    claims = {
        "sub": str(user_id),
        "jti": jti,
        "token_type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at.isoformat()


def decode_token(token: str, expected_type: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    token_type = payload.get("token_type")
    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Expected a {expected_type} token",
        )
    return payload

