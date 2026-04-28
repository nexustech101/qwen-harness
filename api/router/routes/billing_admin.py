from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.modules.billing_errors import raise_mapped_billing_error
from api.router.dependencies import get_admin_user, run_db
from api.schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingPortalResponse,
    BillingSubscriptionPage,
    BillingSubscriptionPublic,
)
from api.services.billing_service import (
    create_checkout_session_for_user_id,
    create_portal_session_for_user_id,
    get_billing_account_for_user,
    list_billing_accounts,
    sync_subscription_for_user_id,
)


router = APIRouter(prefix="/ops/billing", tags=["ops"])


@router.get("/accounts", response_model=BillingSubscriptionPage)
async def billing_accounts_list(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None),
    stripe_customer_id: str | None = Query(default=None),
    stripe_subscription_id: str | None = Query(default=None),
    subscription_status: str | None = Query(default=None),
    price_id: str | None = Query(default=None),
    cancel_at_period_end: bool | None = Query(default=None),
    current_user=Depends(get_admin_user),
):
    del request, current_user
    rows, total = await run_db(
        list_billing_accounts,
        limit=limit,
        offset=offset,
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        subscription_status=subscription_status,
        price_id=price_id,
        cancel_at_period_end=cancel_at_period_end,
    )
    return BillingSubscriptionPage(
        items=[BillingSubscriptionPublic.from_model(item) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}/subscription", response_model=BillingSubscriptionPublic)
async def billing_account_get_for_user(user_id: int, current_user=Depends(get_admin_user)):
    del current_user
    account = await run_db(get_billing_account_for_user, user_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No billing account found for user.")
    return BillingSubscriptionPublic.from_model(account)


@router.post("/users/{user_id}/checkout-session", response_model=BillingCheckoutResponse, status_code=status.HTTP_201_CREATED)
async def billing_checkout_for_user(
    user_id: int,
    payload: BillingCheckoutRequest | None = None,
    current_user=Depends(get_admin_user),
):
    del current_user
    try:
        session = await run_db(
            create_checkout_session_for_user_id,
            user_id,
            payload.price_id if payload else None,
        )
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return BillingCheckoutResponse(**session)


@router.post("/users/{user_id}/portal-session", response_model=BillingPortalResponse)
async def billing_portal_for_user(user_id: int, current_user=Depends(get_admin_user)):
    del current_user
    try:
        session = await run_db(create_portal_session_for_user_id, user_id)
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return BillingPortalResponse(**session)


@router.post("/users/{user_id}/sync", response_model=BillingSubscriptionPublic)
async def billing_sync_for_user(user_id: int, current_user=Depends(get_admin_user)):
    del current_user
    try:
        account = await run_db(sync_subscription_for_user_id, user_id)
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return BillingSubscriptionPublic.from_model(account)
