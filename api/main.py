def main() -> None:
    """Run the API server."""
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, log_level="info", reload=True)

if __name__ == "__main__":
    main()