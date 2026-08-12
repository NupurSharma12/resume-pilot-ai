"""FastAPI dependency for retrieving the configured `PersistenceStore`.

Mirrors `app.api.v1.endpoints.career_conversation.get_conversation_session_store`
and `app.api.v1.endpoints.tailoring_suggestions.get_tailoring_plan_store`
exactly: a `Request`-based dependency, since the store must be the *same*
instance across every request for the lifetime of the app — it is built
once in `create_app` (`app.persistence.factory.build_persistence_store`)
and stashed on `app.state`, the same place those two stores live.

Returns the `PersistenceStore` Protocol type, not `InMemoryPersistenceStore`
or `PostgresPersistenceStore` — endpoints depending on this function only
ever see the structural interface, never which concrete backend is
configured.
"""

from fastapi import Request

from app.persistence.store import PersistenceStore


def get_persistence_store(request: Request) -> PersistenceStore:
    """Return the process-lifetime `PersistenceStore` attached to `app.state`."""
    return request.app.state.persistence_store
