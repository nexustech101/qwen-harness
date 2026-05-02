from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from registers.db import InvalidQueryError, RecordNotFoundError, RegistryError, UniqueConstraintError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.modules.error_handlers import (
    invalid_query_handler,
    not_found_handler,
    registry_error_handler,
    unique_constraint_handler,
)
from api.modules.middleware import observability_middleware
from api.router.rate_limit import limiter, settings
from api.router.routes import build_api_router
from api.modules.dependencies import run_db
from api.router.routes.ws import router as ws_router
from api.config.logging import configure_logging
from api.db.models import dispose_database, initialize_database
from api.integrations.firebase import initialize_firebase

configure_logging(settings)
logger = logging.getLogger("user_api.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_db(initialize_database)
    await run_db(initialize_firebase, settings)
    logger.info(
        "application_startup",
        extra={"event": "application_startup", "details": {"api_version": settings.api_version}},
    )
    yield
    await run_db(dispose_database)
    logger.info("application_shutdown", extra={"event": "application_shutdown"})


def create_app() -> FastAPI:
    app = FastAPI(
        title="Qwen Coder API",
        version=settings.api_version,
        description=(
            "Unified backend API for agent runtime, authenticated chat persistence, "
            "and account/billing/ops endpoints."
        ),
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(UniqueConstraintError, unique_constraint_handler)
    app.add_exception_handler(RecordNotFoundError, not_found_handler)
    app.add_exception_handler(InvalidQueryError, invalid_query_handler)
    app.add_exception_handler(RegistryError, registry_error_handler)

    app.middleware("http")(observability_middleware)
    app.include_router(build_api_router(include_health=False, include_agent_runtime=True), prefix="/api")
    app.include_router(ws_router)
    return app


app = create_app()
