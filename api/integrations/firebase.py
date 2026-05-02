from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from api.config.config import Settings

logger = logging.getLogger("user_api.firebase")

try:
    import firebase_admin
    from firebase_admin import auth, credentials
except Exception:  # pragma: no cover - dependency/import failure handled at runtime
    firebase_admin = None
    auth = None
    credentials = None


def initialize_firebase(settings: Settings) -> None:
    if not settings.firebase_enabled:
        return

    if firebase_admin is None:
        raise RuntimeError("firebase-admin dependency is not available")

    if getattr(firebase_admin, "_apps", None):
        return

    options: dict[str, Any] = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    if settings.firebase_credentials_path:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred, options=options or None)
        logger.info("firebase_initialized_with_certificate")
        return

    firebase_admin.initialize_app(options=options or None)
    logger.info("firebase_initialized_default_credentials")


def verify_firebase_token(id_token: str, settings: Settings) -> dict[str, Any]:
    if not settings.firebase_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is disabled",
        )
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication backend unavailable",
        )

    try:
        claims = auth.verify_id_token(id_token, check_revoked=settings.firebase_check_revoked)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token",
        ) from exc

    expected_project = settings.firebase_project_id
    if expected_project:
        audience = claims.get("aud")
        if audience != expected_project:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firebase token audience mismatch",
            )

    return claims

