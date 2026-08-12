"""Tests for `app.py`'s `lifespan` disposing the configured `PersistenceStore` on shutdown.

Mirrors `test_app_lifespan.py`'s style: enters `lifespan(app)` directly as
an async context manager rather than spinning up a real ASGI server (see
that module's docstring for why). `test_app_persistence_wiring.py` covers
construction (`app.state.persistence_store` is the right type per
backend); this module covers the other half of the lifecycle -- disposal.
"""

from unittest.mock import AsyncMock

import pytest

from app.app import create_app, lifespan
from app.core.config import Settings
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.postgres_store import PostgresPersistenceStore


async def test_memory_backend_starts_and_stops_cleanly_with_no_dispose_call() -> None:
    """The default, zero-configuration backend must work with no database at all."""
    app = create_app(Settings(gemini_api_key="test-key", persistence_backend="memory"))
    assert isinstance(app.state.persistence_store, InMemoryPersistenceStore)

    async with lifespan(app):
        pass

    # Nothing to assert about a dispose call -- InMemoryPersistenceStore
    # has no `dispose` method at all (see app.persistence.lifecycle's
    # Disposable docstring for why one is deliberately not added just for
    # symmetry). The real assertion is the line above: this must not
    # raise, with no RESUMEPILOT_DATABASE_URL set anywhere.
    assert not hasattr(app.state.persistence_store, "dispose")


async def test_postgres_backend_constructs_without_connecting_and_is_disposed_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        gemini_api_key="test-key",
        persistence_backend="postgres",
        database_url="postgresql+asyncpg://user:pw@unreachable-host/db",
    )
    # Constructing the app must not itself attempt a connection -- if it
    # did, this line would hang/fail against the unreachable host above.
    app = create_app(settings)
    assert isinstance(app.state.persistence_store, PostgresPersistenceStore)

    dispose_mock = AsyncMock()
    monkeypatch.setattr(app.state.persistence_store, "dispose", dispose_mock)

    async with lifespan(app):
        dispose_mock.assert_not_called()

    dispose_mock.assert_awaited_once()


async def test_each_app_instance_disposes_only_its_own_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        gemini_api_key="test-key",
        persistence_backend="postgres",
        database_url="postgresql+asyncpg://user:pw@unreachable-host/db",
    )
    first_app = create_app(settings)
    second_app = create_app(settings)
    assert first_app.state.persistence_store is not second_app.state.persistence_store

    first_dispose = AsyncMock()
    second_dispose = AsyncMock()
    monkeypatch.setattr(first_app.state.persistence_store, "dispose", first_dispose)
    monkeypatch.setattr(second_app.state.persistence_store, "dispose", second_dispose)

    async with lifespan(first_app):
        pass

    first_dispose.assert_awaited_once()
    second_dispose.assert_not_called()
