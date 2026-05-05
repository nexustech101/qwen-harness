import uvicorn

from api.router import app, create_app


def main() -> None:
    """Entry point for running the API server."""
    uvicorn.run(
        "api.router:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


__all__ = ["app", "create_app"]

