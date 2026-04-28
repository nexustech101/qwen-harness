from __future__ import annotations

from pydantic import BaseModel, Field

from api.db.models import BillingAccount

ACCESS_GRANTING_STATUSES = {"active", "trialing", "past_due", "unpaid"}


class BillingCheckoutRequest(BaseModel):
    price_id: str | None = Field(default=None, min_length=1, max_length=120)


class BillingCheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str
    customer_id: str


class BillingPortalResponse(BaseModel):
    portal_url: str


class BillingSubscriptionPublic(BaseModel):
    user_id: int
    stripe_customer_id: str
    stripe_subscription_id: str | None = None
    subscription_status: str | None = None
    price_id: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool
    has_access: bool
    updated_at: str

    @classmethod
    def from_model(cls, account: BillingAccount) -> "BillingSubscriptionPublic":
        status = account.subscription_status
        return cls(
            user_id=account.user_id,
            stripe_customer_id=account.stripe_customer_id,
            stripe_subscription_id=account.stripe_subscription_id,
            subscription_status=status,
            price_id=account.price_id,
            current_period_end=account.current_period_end,
            cancel_at_period_end=account.cancel_at_period_end,
            has_access=bool(status in ACCESS_GRANTING_STATUSES),
            updated_at=account.updated_at,
        )


class BillingSubscriptionPage(BaseModel):
    items: list[BillingSubscriptionPublic]
    total: int
    limit: int
    offset: int
