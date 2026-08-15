"""Unit tests for `build_persistence_store` -- where PERSISTENCE_BACKEND is interpreted."""

import pytest

from app.core.config import Settings
from app.persistence.factory import build_persistence_store
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.postgres_store import PostgresPersistenceStore


def test_default_settings_select_memory_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """The field's true default is `memory` -- independent of any developer's local `.env`.

    Same reasoning as `test_persistence_db_engine.py`'s identically
    isolated `test_default_settings_leave_database_url_unset`: `Settings`
    always reads `.env`, so a bare `Settings()` here would otherwise
    reflect whatever `RESUMEPILOT_PERSISTENCE_BACKEND` a developer's own
    `.env` happens to set for local Postgres testing, not this field's
    actual default.
    """
    monkeypatch.delenv("RESUMEPILOT_PERSISTENCE_BACKEND", raising=False)

    assert Settings(_env_file=None).persistence_backend == "memory"


def test_memory_backend_builds_in_memory_store() -> None:
    store = build_persistence_store(Settings(persistence_backend="memory"))

    assert isinstance(store, InMemoryPersistenceStore)


def test_postgres_backend_without_database_url_fails_fast() -> None:
    settings = Settings(persistence_backend="postgres", database_url=None)

    with pytest.raises(ValueError, match="RESUMEPILOT_DATABASE_URL is required"):
        build_persistence_store(settings)


def test_postgres_backend_builds_postgres_store_without_connecting() -> None:
    # No real database is reachable at this URL -- if constructing the
    # store tried to connect, this would hang/fail. It must not: see
    # PostgresPersistenceStore's module docstring.
    settings = Settings(
        persistence_backend="postgres",
        database_url="postgresql+asyncpg://user:pw@unreachable-host/db",
    )

    store = build_persistence_store(settings)

    assert isinstance(store, PostgresPersistenceStore)


async def test_each_call_builds_an_independent_store_instance() -> None:
    settings = Settings(persistence_backend="memory")

    first = build_persistence_store(settings)
    second = build_persistence_store(settings)
    resume = await first.create_resume(name="Alice's resume")

    assert first is not second
    assert await second.get_resume(resume.id) is None
