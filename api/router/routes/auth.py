from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.modules.dependencies import get_current_user, run_db
from api.modules.middleware import request_ip, request_user_agent
from api.router.rate_limit import limiter, settings
from api.config.logging import get_request_id
from api.schemas import (
    FirebaseExchangeRequest,
    FirebaseExchangeResponse,
    LogoutRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserPublic,
)
from api.services.auth_service import (
    authenticate_user,
    exchange_firebase_token,
    issue_tokens_for_user,
    record_auth_event,
    revoke_all_user_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from api.services.user_service import change_password, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.register_rate_limit)
async def register(request: Request, payload: UserCreate):
    user = await run_db(create_user, payload.email, payload.full_name, payload.password, False, None)
    await run_db(
        record_auth_event,
        user.id,
        user.email,
        request_ip(request),
        "register",
        True,
        request_user_agent(request),
        getattr(request.state, "request_id", get_request_id()),
    )
    return UserPublic.from_model(user)


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings.login_rate_limit)
async def login(request: Request, payload: UserLogin):
    user = await run_db(authenticate_user, payload.email, payload.password)
    success = user is not None
    await run_db(
        record_auth_event,
        user.id if user else None,
        payload.email,
        request_ip(request),
        "login",
        success,
        request_user_agent(request),
        getattr(request.state, "request_id", get_request_id()),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    tokens = await run_db(issue_tokens_for_user, user)
    return TokenPair(**tokens)


@router.post("/firebase/exchange", response_model=FirebaseExchangeResponse)
@limiter.limit(settings.firebase_exchange_rate_limit)
async def firebase_exchange(request: Request, payload: FirebaseExchangeRequest):
    try:
        user, tokens = await run_db(exchange_firebase_token, payload.id_token, payload.create_if_missing)
    except HTTPException as exc:
        await run_db(
            record_auth_event,
            None,
            "firebase:unknown",
            request_ip(request),
            "firebase_exchange",
            False,
            request_user_agent(request),
            getattr(request.state, "request_id", get_request_id()),
            {"error": exc.detail},
        )
        raise

    await run_db(
        record_auth_event,
        user.id,
        user.email,
        request_ip(request),
        "firebase_exchange",
        True,
        request_user_agent(request),
        getattr(request.state, "request_id", get_request_id()),
    )
    return FirebaseExchangeResponse(user=UserPublic.from_model(user), **tokens)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.refresh_rate_limit)
async def refresh_token(request: Request, payload: RefreshRequest):
    del request
    tokens = await run_db(rotate_refresh_token, payload.refresh_token)
    return TokenPair(**tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.refresh_rate_limit)
async def logout(request: Request, payload: LogoutRequest, current_user=Depends(get_current_user)):
    del request
    if payload.refresh_token:
        await run_db(revoke_refresh_token, payload.refresh_token)
    else:
        await run_db(revoke_all_user_sessions, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
async def me(current_user=Depends(get_current_user)):
    return UserPublic.from_model(current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.change_password_rate_limit)
async def change_my_password(
    request: Request,
    payload: PasswordChangeRequest,
    current_user=Depends(get_current_user),
):
    del request
    changed = await run_db(change_password, current_user.id, payload.current_password, payload.new_password)
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    await run_db(revoke_all_user_sessions, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

