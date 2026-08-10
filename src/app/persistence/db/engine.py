"""Resolves the SQLAlchemy connection URL for the configured PostgreSQL database.

Used today only by Alembic's `migrations/env.py`, to connect for running
migrations. A future `PostgresPersistenceStore` milestone will reuse
`get_database_url` the same way to construct its own (likely
pooled/shared) `AsyncEngine` -- that engine's lifecycle management
(creation once at app startup, disposal at shutdown, pool sizing) is
deliberately not built here, since nothing in this phase runs application
queries against PostgreSQL yet.
"""

from app.core.config import Settings


def get_database_url(settings: Settings) -> str:
    """Return `settings.database_url`, the SQLAlchemy async URL for the PostgreSQL database.

    Raises `ValueError` if unset. Only ever called once `postgres` has
    already been selected (by `env.py`, or a future
    `PostgresPersistenceStore`) -- at that point a missing URL is a real
    misconfiguration, unlike under `PERSISTENCE_BACKEND=memory`, where it
    is expected to be unset and never read.

    Expected form: `postgresql+asyncpg://user:password@host/dbname?ssl=require`
    -- the `+asyncpg` driver segment, matching the `asyncpg` dependency
    this project uses for async PostgreSQL access. A Neon *pooled*
    connection string (recommended for a serverless-style app -- see
    `.env.example`) uses the same `postgresql://` scheme; only the driver
    segment needs adding, nothing Neon-specific about the rest of the URL.
    """
    if not settings.database_url:
        raise ValueError(
            "RESUMEPILOT_DATABASE_URL is required when PERSISTENCE_BACKEND=postgres, "
            "but was not set."
        )
    return settings.database_url
