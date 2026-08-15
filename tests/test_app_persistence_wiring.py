"""Tests that `create_app` wires `app.state.persistence_store` per `PERSISTENCE_BACKEND`.

Mirrors `test_app_lifespan.py`'s style: constructs `Settings`/`create_app`
directly rather than going through the shared `client` fixture, since what's
under test is `app.state` at construction time, not request handling.
"""

from app.app import create_app
from app.core.config import Settings
from app.persistence.memory_store import InMemoryPersistenceStore


def test_default_settings_wire_an_in_memory_persistence_store() -> None:
    # `persistence_backend="memory"` pinned explicitly, not left to
    # `Settings`' own default -- `Settings` always reads `.env`, so an
    # unpinned `Settings()` here would instead reflect whatever
    # `RESUMEPILOT_PERSISTENCE_BACKEND` a developer's own `.env` sets for
    # local Postgres testing. (The field's *actual* default is covered by
    # `test_persistence_factory.py::test_default_settings_select_memory_backend`,
    # which isolates from `.env` specifically to test that.) What this
    # test is really asserting -- "given memory backend, create_app wires
    # an InMemoryPersistenceStore" -- doesn't need the ambient default at
    # all.
    app = create_app(Settings(gemini_api_key="test-key", persistence_backend="memory"))

    assert isinstance(app.state.persistence_store, InMemoryPersistenceStore)


async def test_each_app_instance_gets_its_own_persistence_store() -> None:
    first_app = create_app(Settings(gemini_api_key="test-key", persistence_backend="memory"))
    second_app = create_app(Settings(gemini_api_key="test-key", persistence_backend="memory"))

    resume = await first_app.state.persistence_store.create_resume(name="Alice's resume")

    assert first_app.state.persistence_store is not second_app.state.persistence_store
    assert await second_app.state.persistence_store.get_resume(resume.id) is None
