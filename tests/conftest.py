import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Required settings (e.g. gemini_api_key) have no default, so app.app's
# module-level `app = create_app()` singleton needs this set in the
# environment *before* app.app is imported below, independent of the
# `settings` fixture (which only affects `create_app` calls made by tests).
os.environ.setdefault("RESUMEPILOT_GEMINI_API_KEY", "test-gemini-api-key")

from app.app import create_app  # noqa: E402
from app.core.config import Settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(log_json=False, gemini_api_key="test-gemini-api-key")


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
