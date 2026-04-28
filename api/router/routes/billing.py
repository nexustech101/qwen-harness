from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.modules.billing_errors import raise_mapped_billing_error
from api.router.dependencies import get_current_user, run_db
from api.modules.rate_limit import limiter, settings
from api.schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingPortalResponse,
    BillingSubscriptionPublic,
)
from api.services.billing_service import (
    create_checkout_session_for_user,
    create_portal_session_for_user,
    get_billing_account_for_user,
    process_webhook_event,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=BillingSubscriptionPublic)
async def get_my_billing_subscription(current_user=Depends(get_current_user)):
    account = await run_db(get_billing_account_for_user, current_user.id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No billing account found for user.")
    return BillingSubscriptionPublic.from_model(account)


@router.post("/checkout-session", response_model=BillingCheckoutResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.billing_checkout_rate_limit)
async def create_checkout_session(
    request: Request,
    payload: BillingCheckoutRequest,
    current_user=Depends(get_current_user),
):
    del request
    try:
        session = await run_db(create_checkout_session_for_user, current_user, payload.price_id)
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return BillingCheckoutResponse(**session)


@router.post("/portal-session", response_model=BillingPortalResponse)
@limiter.limit(settings.billing_portal_rate_limit)
async def create_billing_portal_session(request: Request, current_user=Depends(get_current_user)):
    del request
    try:
        session = await run_db(create_portal_session_for_user, current_user)
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return BillingPortalResponse(**session)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.billing_webhook_rate_limit)
async def stripe_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    try:
        await run_db(process_webhook_event, body, signature)
    except Exception as exc:
        raise_mapped_billing_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
