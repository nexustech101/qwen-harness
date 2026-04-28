from __future__ import annotations

from typing import Any

from api.config.config import Settings

STRIPE_API_VERSION = "2026-02-25.clover"

try:
    import stripe as stripe_sdk
except ModuleNotFoundError:
    stripe_sdk = None


class StripeConfigurationError(RuntimeError):
    """Raised when Stripe settings are missing or disabled."""


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    raise TypeError("Unexpected Stripe response type")


def _require_sdk():
    if stripe_sdk is None:
        raise StripeConfigurationError(
            "Stripe SDK is not installed. Install dependency `stripe` to enable billing.",
        )
    return stripe_sdk


def _configure(settings: Settings):
    if not settings.stripe_enabled:
        raise StripeConfigurationError("Stripe billing is disabled.")
    if not settings.stripe_secret_key:
        raise StripeConfigurationError("Stripe secret key is not configured.")

    sdk = _require_sdk()
    sdk.api_key = settings.stripe_secret_key
    sdk.api_version = STRIPE_API_VERSION
    return sdk


def create_customer(
    *,
    settings: Settings,
    email: str,
    name: str,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    sdk = _configure(settings)
    customer = sdk.Customer.create(email=email, name=name, metadata=metadata or {})
    return _to_dict(customer)


def create_checkout_session(
    *,
    settings: Settings,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    client_reference_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    sdk = _configure(settings)
    session = sdk.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=client_reference_id,
        metadata=metadata or {},
    )
    return _to_dict(session)


def create_billing_portal_session(
    *,
    settings: Settings,
    customer_id: str,
    return_url: str,
) -> dict[str, Any]:
    sdk = _configure(settings)
    session = sdk.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return _to_dict(session)


def retrieve_subscription(*, settings: Settings, subscription_id: str) -> dict[str, Any]:
    sdk = _configure(settings)
    subscription = sdk.Subscription.retrieve(subscription_id)
    return _to_dict(subscription)


def construct_event(
    *,
    settings: Settings,
    payload: bytes,
    signature: str | None,
) -> dict[str, Any]:
    if not settings.stripe_webhook_secret:
        raise StripeConfigurationError("Stripe webhook secret is not configured.")
    if not signature:
        raise ValueError("Missing Stripe-Signature header.")

    sdk = _configure(settings)
    event = sdk.Webhook.construct_event(payload=payload, sig_header=signature, secret=settings.stripe_webhook_secret)
    return _to_dict(event)
