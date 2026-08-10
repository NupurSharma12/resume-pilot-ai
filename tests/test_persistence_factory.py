"""Unit tests for `build_persistence_store` -- where PERSISTENCE_BACKEND is interpreted."""

import pytest

from app.core.config import Settings
from app.persistence.factory import build_persistence_store
from app.persistence.memory_store import InMemoryPersistenceStore


def test_default_settings_select_memory_backend() -> None:
    assert Settings().persistence_backend == "memory"


def test_memory_backend_builds_in_memory_store() -> None:
    store = build_persistence_store(Settings(persistence_backend="memory"))

    assert isinstance(store, InMemoryPersistenceStore)


def test_postgres_backend_fails_fast_as_not_yet_implemented() -> None:
    settings = Settings(persistence_backend="postgres")

    with pytest.raises(NotImplementedError, match="not implemented yet"):
        build_persistence_store(settings)


def test_each_call_builds_an_independent_store_instance() -> None:
    settings = Settings(persistence_backend="memory")

    first = build_persistence_store(settings)
    second = build_persistence_store(settings)
    resume = first.create_resume(name="Alice's resume")

    assert first is not second
    assert second.get_resume(resume.id) is None
