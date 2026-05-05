from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from registers.db import InvalidQueryError, RecordNotFoundError, RegistryError, UniqueConstraintError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.config.config import get_settings
from api.config.logging import configure_logging
from api.db.models import dispose_database, initialize_database
from api.modules.error_handlers import (
    invalid_query_handler,
    not_found_handler,
    registry_error_handler,
    unique_constraint_handler,
)
from api.modules.middleware import observability_middleware
from api.modules.rate_limit import limiter
from api.router.routes import build_api_router

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("agent_api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(initialize_database)
    logger.info("application_startup", extra={"event": "startup", "version": settings.api_version})

    # Register MCP tools and prompts (side-effect imports)
    import api.mcp.tools    # noqa: F401
    import api.mcp.prompts  # noqa: F401

    yield

    await asyncio.to_thread(dispose_database)
    logger.info("application_shutdown", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    from api.mcp.server import mcp  # imported here to avoid circular import at module level

    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # registers.db error handlers
    app.add_exception_handler(UniqueConstraintError, unique_constraint_handler)
    app.add_exception_handler(RecordNotFoundError, not_found_handler)
    app.add_exception_handler(InvalidQueryError, invalid_query_handler)
    app.add_exception_handler(RegistryError, registry_error_handler)

    # Observability middleware
    app.middleware("http")(observability_middleware)

    # REST + WebSocket routes
    app.include_router(build_api_router(), prefix="/api")

    # MCP server mounted at /mcp
    app.mount("/mcp", mcp.http_app())

    return app


app = create_app()
