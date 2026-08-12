"""Tests for `app.persistence.dependencies.get_persistence_store`."""

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.persistence.dependencies import get_persistence_store
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.store import PersistenceStore


async def test_returns_the_store_attached_to_app_state() -> None:
    app = FastAPI()
    sentinel_store = InMemoryPersistenceStore()
    app.state.persistence_store = sentinel_store

    @app.get("/probe")
    async def probe(store: PersistenceStore = Depends(get_persistence_store)) -> dict:
        return {"is_sentinel": store is sentinel_store}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"is_sentinel": True}


async def test_a_handler_depending_on_the_protocol_works_against_any_conforming_store() -> None:
    """An endpoint depending on `PersistenceStore` must not care which concrete backend it holds.

    Overrides `get_persistence_store` with a minimal hand-written double
    that satisfies the `PersistenceStore` Protocol structurally (same
    method names/signatures) but is neither `InMemoryPersistenceStore`
    nor `PostgresPersistenceStore` -- proving the dependency (and any
    endpoint built on it) only relies on the structural interface.
    """

    class _FakeStore:
        async def create_resume(self, name: str):
            return "fake-resume"

    app = FastAPI()
    app.state.persistence_store = InMemoryPersistenceStore()
    app.dependency_overrides[get_persistence_store] = lambda: _FakeStore()

    @app.get("/probe")
    async def probe(store: PersistenceStore = Depends(get_persistence_store)) -> dict:
        resume = await store.create_resume(name="whatever")
        return {"resume": resume}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"resume": "fake-resume"}
