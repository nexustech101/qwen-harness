from fastapi import APIRouter

from .system import router as system_router
from .chat import router as chat_router
from .uploads import router as uploads_router
from .workflows import router as workflows_router
from .ws import router as ws_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(system_router)
    router.include_router(chat_router)
    router.include_router(uploads_router)
    router.include_router(workflows_router)
    router.include_router(ws_router)
    return router
