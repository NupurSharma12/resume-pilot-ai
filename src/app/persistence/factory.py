"""Builds the configured `PersistenceStore` from `Settings`.

Mirrors `app.gateways.llm.factory.build_llm_gateway`: the single place
that maps configuration (`RESUMEPILOT_PERSISTENCE_BACKEND`) onto a
concrete `PersistenceStore` implementation, so introducing a new backend
(or changing the default) is a one-place change. `app.py`'s `create_app`
calls this once per app instance and attaches the result to
`app.state.persistence_store`, the same process-lifetime-singleton
treatment `ConversationSessionStore`/`TailoringPlanStore` already get.
"""

from app.core.config import Settings
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.store import PersistenceStore

_BUILDERS = {
    "memory": lambda: InMemoryPersistenceStore(),
}


def build_persistence_store(settings: Settings) -> PersistenceStore:
    """Build the `PersistenceStore` named by `settings.persistence_backend`.

    `postgres` is a recognized `Settings.persistence_backend` value (see
    `Settings`'s field description) but has no builder yet -- selecting it
    raises `NotImplementedError` immediately rather than silently falling
    back to `memory`, so a developer who sets
    `RESUMEPILOT_PERSISTENCE_BACKEND=postgres` before that milestone exists
    gets a clear, immediate failure instead of a confusing "why isn't
    anything being saved" bug.
    """
    if settings.persistence_backend == "postgres":
        raise NotImplementedError(
            "PERSISTENCE_BACKEND=postgres is not implemented yet -- it is reserved for a "
            "later milestone. Use PERSISTENCE_BACKEND=memory (the default) for now."
        )
    builder = _BUILDERS[settings.persistence_backend]
    return builder()
