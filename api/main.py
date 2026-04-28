from api.router import app, create_app

def main() -> None:
    """Entry point for running the API server."""
    app = create_app()
    app.run(host="0.0.0.0", port=8000)

__all__ = ["app", "create_app"]

