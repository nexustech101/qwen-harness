from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from registers.db import RecordNotFoundError

from api.config.config import get_settings
from api.config.security import utc_now_iso
from api.db.models import BillingAccount, User
from api.integrations import stripe as stripe_integration

logger = logging.getLogger("user_api.services.billing")


class BillingConfigurationError(RuntimeError):
    """Raised when local billing configuration is missing or disabled."""


class BillingProviderError(RuntimeError):
    """Raised when Stripe provider operations fail."""


class BillingWebhookError(BillingProviderError):
    """Raised when webhook verification or parsing fails."""


def _now() -> str:
    return utc_now_iso()


def _ts_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _extract_price_id(subscription_payload: dict[str, Any]) -> str | None:
    items = subscription_payload.get("items", {})
    data = items.get("data", []) if isinstance(items, dict) else []
    if not data:
        return None

    price = data[0].get("price", {})
    if isinstance(price, dict):
        return price.get("id")
    return None


def _apply_subscription_payload(account: BillingAccount, subscription_payload: dict[str, Any]) -> None:
    account.stripe_subscription_id = subscription_payload.get("id") or account.stripe_subscription_id
    account.subscription_status = subscription_payload.get("status")
    account.cancel_at_period_end = bool(subscription_payload.get("cancel_at_period_end", False))
    account.current_period_end = _ts_to_iso(subscription_payload.get("current_period_end"))
    account.price_id = _extract_price_id(subscription_payload) or account.price_id
    account.updated_at = _now()
    account.save()


def _ensure_config_for_checkout(price_id: str | None) -> str:
    settings = get_settings()
    selected = price_id or settings.stripe_default_price_id
    if not selected:
        raise BillingConfigurationError(
            "No Stripe price configured. Set USER_API_STRIPE_DEFAULT_PRICE_ID or provide `price_id`.",
        )
    return selected


def get_billing_account_for_user(user_id: int) -> BillingAccount | None:
    try:
        return BillingAccount.objects.require(user_id=user_id)
    except RecordNotFoundError:
        return None


def list_billing_accounts(
    *,
    limit: int,
    offset: int,
    user_id: int | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    subscription_status: str | None = None,
    price_id: str | None = None,
    cancel_at_period_end: bool | None = None,
) -> tuple[list[BillingAccount], int]:
    filters: dict[str, Any] = {}
    if user_id is not None:
        filters["user_id"] = user_id
    if stripe_customer_id:
        filters["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        filters["stripe_subscription_id"] = stripe_subscription_id
    if subscription_status:
        filters["subscription_status"] = subscription_status
    if price_id:
        filters["price_id"] = price_id
    if cancel_at_period_end is not None:
        filters["cancel_at_period_end"] = cancel_at_period_end

    rows = BillingAccount.objects.filter(order_by="-id", limit=limit, offset=offset, **filters)
    total = BillingAccount.objects.count(**filters)
    return rows, total


def _require_user(user_id: int) -> User:
    return User.objects.require(user_id)


def _create_account_for_user(user: User) -> BillingAccount:
    if user.id is None:
        raise BillingProviderError("User has no persisted ID.")

    settings = get_settings()
    try:
        customer = stripe_integration.create_customer(
            settings=settings,
            email=user.email,
            name=user.full_name,
            metadata={"user_id": str(user.id)},
        )
    except stripe_integration.StripeConfigurationError as exc:
        raise BillingConfigurationError(str(exc)) from exc
    except Exception as exc:
        raise BillingProviderError("Failed to create Stripe customer.") from exc

    now = _now()
    return BillingAccount.objects.create(
        user_id=user.id,
        stripe_customer_id=str(customer.get("id")),
        stripe_subscription_id=None,
        subscription_status=None,
        price_id=None,
        current_period_end=None,
        cancel_at_period_end=False,
        created_at=now,
        updated_at=now,
    )


def _get_or_create_account(user: User) -> BillingAccount:
    if user.id is None:
        raise BillingProviderError("User has no persisted ID.")
    existing = get_billing_account_for_user(user.id)
    if existing:
        return existing
    return _create_account_for_user(user)


def create_checkout_session_for_user(user: User, price_id: str | None = None) -> dict[str, str]:
    if user.id is None:
        raise BillingProviderError("User has no persisted ID.")

    account = _get_or_create_account(user)
    selected_price = _ensure_config_for_checkout(price_id)
    settings = get_settings()

    try:
        session = stripe_integration.create_checkout_session(
            settings=settings,
            customer_id=account.stripe_customer_id,
            price_id=selected_price,
            success_url=settings.stripe_success_url,
            cancel_url=settings.stripe_cancel_url,
            client_reference_id=str(user.id),
            metadata={"user_id": str(user.id)},
        )
    except stripe_integration.StripeConfigurationError as exc:
        raise BillingConfigurationError(str(exc)) from exc
    except Exception as exc:
        raise BillingProviderError("Failed to create Stripe checkout session.") from exc

    account.price_id = selected_price
    account.updated_at = _now()
    account.save()

    subscription_id = session.get("subscription")
    if subscription_id:
        try:
            subscription = stripe_integration.retrieve_subscription(
                settings=settings,
                subscription_id=str(subscription_id),
            )
            _apply_subscription_payload(account, subscription)
        except Exception:
            # Best effort only. Authoritative state will arrive via webhook.
            pass

    checkout_url = session.get("url")
    session_id = session.get("id")
    if not checkout_url or not session_id:
        raise BillingProviderError("Stripe checkout session is missing required fields.")

    return {
        "session_id": str(session_id),
        "checkout_url": str(checkout_url),
        "customer_id": account.stripe_customer_id,
    }


def create_checkout_session_for_user_id(user_id: int, price_id: str | None = None) -> dict[str, str]:
    return create_checkout_session_for_user(_require_user(user_id), price_id)


def create_portal_session_for_user(user: User) -> dict[str, str]:
    if user.id is None:
        raise BillingProviderError("User has no persisted ID.")
    account = get_billing_account_for_user(user.id)
    if not account:
        raise BillingProviderError("No billing profile exists for this user.")

    settings = get_settings()
    try:
        session = stripe_integration.create_billing_portal_session(
            settings=settings,
            customer_id=account.stripe_customer_id,
            return_url=settings.stripe_portal_return_url,
        )
    except stripe_integration.StripeConfigurationError as exc:
        raise BillingConfigurationError(str(exc)) from exc
    except Exception as exc:
        raise BillingProviderError("Failed to create Stripe billing portal session.") from exc

    portal_url = session.get("url")
    if not portal_url:
        raise BillingProviderError("Stripe portal session is missing URL.")
    return {"portal_url": str(portal_url)}


def create_portal_session_for_user_id(user_id: int) -> dict[str, str]:
    return create_portal_session_for_user(_require_user(user_id))


def sync_subscription_for_user(user: User) -> BillingAccount:
    if user.id is None:
        raise BillingProviderError("User has no persisted ID.")

    account = get_billing_account_for_user(user.id)
    if not account:
        raise BillingProviderError("No billing profile exists for this user.")
    if not account.stripe_subscription_id:
        raise BillingProviderError("No Stripe subscription is linked for this user.")

    settings = get_settings()
    try:
        subscription = stripe_integration.retrieve_subscription(
            settings=settings,
            subscription_id=account.stripe_subscription_id,
        )
    except stripe_integration.StripeConfigurationError as exc:
        raise BillingConfigurationError(str(exc)) from exc
    except Exception as exc:
        raise BillingProviderError("Failed to sync Stripe subscription state.") from exc

    _apply_subscription_payload(account, subscription)
    return account


def sync_subscription_for_user_id(user_id: int) -> BillingAccount:
    return sync_subscription_for_user(_require_user(user_id))


def _get_or_create_account_for_webhook(
    customer_id: str,
    client_reference_id: str | None,
) -> BillingAccount | None:
    try:
        return BillingAccount.objects.require(stripe_customer_id=customer_id)
    except RecordNotFoundError:
        if not client_reference_id:
            return None

    try:
        user_id = int(client_reference_id)
    except (TypeError, ValueError):
        return None

    try:
        User.objects.require(user_id)
    except RecordNotFoundError:
        return None

    now = _now()
    return BillingAccount.objects.create(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=None,
        subscription_status=None,
        price_id=None,
        current_period_end=None,
        cancel_at_period_end=False,
        created_at=now,
        updated_at=now,
    )


def _handle_checkout_completed(payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer")
    if not customer_id:
        return

    account = _get_or_create_account_for_webhook(
        customer_id=str(customer_id),
        client_reference_id=payload.get("client_reference_id"),
    )
    if not account:
        return

    subscription_id = payload.get("subscription")
    if subscription_id:
        account.stripe_subscription_id = str(subscription_id)
        account.updated_at = _now()
        account.save()

        settings = get_settings()
        try:
            subscription = stripe_integration.retrieve_subscription(
                settings=settings,
                subscription_id=str(subscription_id),
            )
            _apply_subscription_payload(account, subscription)
        except Exception:
            logger.warning(
                "billing_subscription_lookup_failed",
                extra={
                    "event": "billing_subscription_lookup_failed",
                    "details": {"subscription_id": str(subscription_id), "customer_id": str(customer_id)},
                },
            )


def _handle_subscription_event(payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer")
    if not customer_id:
        return

    try:
        account = BillingAccount.objects.require(stripe_customer_id=str(customer_id))
    except RecordNotFoundError:
        return

    _apply_subscription_payload(account, payload)


def process_webhook_event(payload: bytes, signature: str | None) -> str:
    settings = get_settings()
    try:
        event = stripe_integration.construct_event(settings=settings, payload=payload, signature=signature)
    except stripe_integration.StripeConfigurationError as exc:
        raise BillingConfigurationError(str(exc)) from exc
    except ValueError as exc:
        raise BillingWebhookError(str(exc)) from exc
    except Exception as exc:
        raise BillingWebhookError("Failed to verify Stripe webhook event.") from exc

    event_type = str(event.get("type", ""))
    event_payload = event.get("data", {}).get("object", {})
    if not isinstance(event_payload, dict):
        raise BillingWebhookError("Malformed Stripe webhook payload.")

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event_payload)
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        _handle_subscription_event(event_payload)

    logger.info(
        "billing_webhook_processed",
        extra={"event": "billing_webhook_processed", "details": {"type": event_type}},
    )
    return event_type
