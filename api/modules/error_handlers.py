from fastapi import Request
from fastapi.responses import JSONResponse
from registers.db import InvalidQueryError, RecordNotFoundError, RegistryError, UniqueConstraintError


async def unique_constraint_handler(_request: Request, exc: UniqueConstraintError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def not_found_handler(_request: Request, exc: RecordNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def invalid_query_handler(_request: Request, exc: InvalidQueryError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def registry_error_handler(_request: Request, exc: RegistryError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

