from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.app import create_app
from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(log_json=False)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
