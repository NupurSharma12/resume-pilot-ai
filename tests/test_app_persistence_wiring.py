"""Tests that `create_app` wires `app.state.persistence_store` per `PERSISTENCE_BACKEND`.

Mirrors `test_app_lifespan.py`'s style: constructs `Settings`/`create_app`
directly rather than going through the shared `client` fixture, since what's
under test is `app.state` at construction time, not request handling.
"""

from app.app import create_app
from app.core.config import Settings
from app.persistence.memory_store import InMemoryPersistenceStore


def test_default_settings_wire_an_in_memory_persistence_store() -> None:
    app = create_app(Settings(gemini_api_key="test-key"))

    assert isinstance(app.state.persistence_store, InMemoryPersistenceStore)


def test_each_app_instance_gets_its_own_persistence_store() -> None:
    first_app = create_app(Settings(gemini_api_key="test-key"))
    second_app = create_app(Settings(gemini_api_key="test-key"))

    resume = first_app.state.persistence_store.create_resume(name="Alice's resume")

    assert first_app.state.persistence_store is not second_app.state.persistence_store
    assert second_app.state.persistence_store.get_resume(resume.id) is None
