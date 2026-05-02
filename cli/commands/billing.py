from __future__ import annotations

import json
from typing import Any

from registers.cli import CommandRegistry

from cli.bootstrap import bootstrap
from api.schemas.billing import ACCESS_GRANTING_STATUSES
from api.services.billing_service import (
    BillingConfigurationError,
    BillingProviderError,
    create_checkout_session_for_user,
    create_portal_session_for_user,
    get_billing_account_for_user,
    sync_subscription_for_user,
)
from api.services.user_service import get_user_by_id


cli = CommandRegistry()


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _account_payload(action: str, user_id: int, account) -> dict[str, Any]:
    status = account.subscription_status
    return {
        "action": action,
        "user_id": user_id,
        "stripe_customer_id": account.stripe_customer_id,
        "stripe_subscription_id": account.stripe_subscription_id,
        "subscription_status": status,
        "price_id": account.price_id,
        "current_period_end": account.current_period_end,
        "cancel_at_period_end": account.cancel_at_period_end,
        "has_access": bool(status in ACCESS_GRANTING_STATUSES),
        "updated_at": account.updated_at,
    }


def _billing_error(action: str, user_id: int, detail: str, code: str = "billing_error") -> str:
    return _to_json({"action": action, "user_id": user_id, "error": code, "detail": detail})


@cli.register(name="billing-status", description="Show local billing state for a user")
@cli.argument("user_id", type=int, help="User ID")
@cli.alias("--billing-status")
def billing_status_command(user_id: int) -> str:
    bootstrap()
    account = get_billing_account_for_user(user_id)
    if not account:
        return _billing_error("billing-status", user_id, "No billing profile exists for this user.", "not_found")
    return _to_json(_account_payload("billing-status", user_id, account))


@cli.register(name="billing-create-checkout", description="Create a Stripe Checkout session for a user")
@cli.argument("user_id", type=int, help="User ID")
@cli.argument("price_id", type=str, default="", help="Optional Stripe Price ID override")
@cli.alias("--billing-create-checkout")
def billing_create_checkout_command(user_id: int, price_id: str = "") -> str:
    bootstrap()
    user = get_user_by_id(user_id)
    try:
        session = create_checkout_session_for_user(user, price_id.strip() or None)
    except BillingConfigurationError as exc:
        return _billing_error("billing-create-checkout", user_id, str(exc), "configuration_error")
    except BillingProviderError as exc:
        return _billing_error("billing-create-checkout", user_id, str(exc))
    return _to_json({"action": "billing-create-checkout", "user_id": user_id, **session})


@cli.register(name="billing-create-portal", description="Create a Stripe Billing Portal session for a user")
@cli.argument("user_id", type=int, help="User ID")
@cli.alias("--billing-create-portal")
def billing_create_portal_command(user_id: int) -> str:
    bootstrap()
    user = get_user_by_id(user_id)
    try:
        session = create_portal_session_for_user(user)
    except BillingConfigurationError as exc:
        return _billing_error("billing-create-portal", user_id, str(exc), "configuration_error")
    except BillingProviderError as exc:
        return _billing_error("billing-create-portal", user_id, str(exc))
    return _to_json({"action": "billing-create-portal", "user_id": user_id, **session})


@cli.register(name="billing-sync", description="Sync local subscription status for a user from Stripe")
@cli.argument("user_id", type=int, help="User ID")
@cli.alias("--billing-sync")
def billing_sync_command(user_id: int) -> str:
    bootstrap()
    user = get_user_by_id(user_id)
    try:
        account = sync_subscription_for_user(user)
    except BillingConfigurationError as exc:
        return _billing_error("billing-sync", user_id, str(exc), "configuration_error")
    except BillingProviderError as exc:
        return _billing_error("billing-sync", user_id, str(exc))
    return _to_json(_account_payload("billing-sync", user_id, account))
