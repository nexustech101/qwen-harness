from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from api.modules.dependencies import get_admin_user, get_current_user, run_db
from api.modules.rate_limit import limiter, settings
from api.schemas import UserPage, UserPublic, UserUpdate
from api.services.auth_service import revoke_all_user_sessions
from api.services.user_service import deactivate_user, get_user_by_id, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserPage)
@limiter.limit(settings.list_users_rate_limit)
async def users_list(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    is_active: bool | None = Query(default=None),
    current_user=Depends(get_admin_user),
):
    del request, current_user
    rows, total = await run_db(list_users, limit, offset, is_active)
    return UserPage(
        items=[UserPublic.from_model(user) for user in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=UserPublic)
async def users_get(user_id: int, current_user=Depends(get_current_user)):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    user = await run_db(get_user_by_id, user_id)
    return UserPublic.from_model(user)


@router.patch("/{user_id}", response_model=UserPublic)
async def users_patch(user_id: int, payload: UserUpdate, current_user=Depends(get_current_user)):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        user = await run_db(update_user, user_id, payload, bool(current_user.is_admin))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return UserPublic.from_model(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def users_deactivate(user_id: int, current_user=Depends(get_admin_user)):
    del current_user
    await run_db(deactivate_user, user_id)
    await run_db(revoke_all_user_sessions, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
