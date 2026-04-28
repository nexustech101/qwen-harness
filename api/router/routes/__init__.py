from fastapi import APIRouter

from .auth import router as auth_router
from .billing import router as billing_router
from .billing_admin import router as billing_admin_router
from .health import router as health_router
from .ops import router as ops_router
from .runtime_health import router as runtime_health_router
from .runtime_sessions import router as runtime_sessions_router
from .runtime_system import router as runtime_system_router
from .users import router as users_router


def build_api_router(
    include_health: bool = False,
    include_agent_runtime: bool = True,
) -> APIRouter:
    router = APIRouter()
    if include_health:
        router.include_router(health_router)
    if include_agent_runtime:
        router.include_router(runtime_health_router)
        router.include_router(runtime_system_router)
        router.include_router(runtime_sessions_router)
    router.include_router(auth_router)
    router.include_router(billing_router)
    router.include_router(billing_admin_router)
    router.include_router(users_router)
    router.include_router(ops_router)
    return router
