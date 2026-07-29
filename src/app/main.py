import uvicorn

from app.core.config import get_settings


def run() -> None:
    """Entrypoint for `uv run resumepilot` / `python -m app.main`."""
    settings = get_settings()
    uvicorn.run(
        "app.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,
    )


if __name__ == "__main__":
    run()
