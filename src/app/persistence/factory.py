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
from app.persistence.db.engine import get_database_url
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.postgres_store import PostgresPersistenceStore
from app.persistence.store import PersistenceStore

_BUILDERS = {
    "memory": lambda settings: InMemoryPersistenceStore(),
    # `get_database_url` raises `ValueError` immediately if
    # `settings.database_url` is unset -- this is what makes selecting
    # `postgres` without `RESUMEPILOT_DATABASE_URL` fail fast, right here
    # at construction time, rather than confusingly on the first read/write.
    # `PostgresPersistenceStore.__init__` itself does not connect (see its
    # own docstring) -- it only configures a lazy `AsyncEngine`/connection
    # pool, the same "no I/O at construction time" guarantee as before.
    "postgres": lambda settings: PostgresPersistenceStore(get_database_url(settings)),
}


def build_persistence_store(settings: Settings) -> PersistenceStore:
    """Build the `PersistenceStore` named by `settings.persistence_backend`.

    Never itself opens a database connection, for either backend --
    `InMemoryPersistenceStore()` is a plain dict-backed object, and
    `PostgresPersistenceStore` only configures a (lazy) connection
    factory; the first real connection attempt happens whenever a caller
    actually invokes a method on the returned store, not here. There is
    no "unknown backend" branch here (unlike `build_llm_gateway`'s):
    `Settings.persistence_backend` is a `Literal["memory", "postgres"]`,
    so an invalid value is already rejected at `Settings()` construction,
    before this function ever runs.
    """
    return _BUILDERS[settings.persistence_backend](settings)
