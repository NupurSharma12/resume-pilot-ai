"""Resolves the SQLAlchemy connection URL for the configured PostgreSQL database.

Used by Alembic's `migrations/env.py` to connect for running migrations,
and by `app.persistence.factory.build_persistence_store` to fail fast when
`persistence_backend="postgres"` is selected without `database_url` set --
in both cases, just resolving a connection string, never opening a
connection itself (see `PostgresPersistenceStore`'s own docstring for how
and when it actually connects).
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
