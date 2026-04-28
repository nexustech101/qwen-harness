from fastapi import APIRouter, Request

from api.modules.middleware import request_ip
from api.router.rate_limit import limiter, settings
from api.config.logging import get_request_id
from api.config.security import utc_now_iso

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.limit(settings.health_rate_limit)
async def health(request: Request):
    return {
        "status": "ok",
        "service": settings.app_name,
        "time": utc_now_iso(),
        "ip": request_ip(request),
        "request_id": getattr(request.state, "request_id", get_request_id()),
    }

