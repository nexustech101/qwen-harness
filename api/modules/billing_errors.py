from __future__ import annotations

from fastapi import HTTPException, status

from api.services.billing_service import (
    BillingConfigurationError,
    BillingProviderError,
    BillingWebhookError,
)


def raise_mapped_billing_error(exc: Exception) -> None:
    if isinstance(exc, BillingConfigurationError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if isinstance(exc, BillingWebhookError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, BillingProviderError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    raise exc
