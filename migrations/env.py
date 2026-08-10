import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import Settings

# Import every ORM table module here (not just `Base`) so `Base.metadata`
# is fully populated before autogenerate runs -- a module that's never
# imported never registers its tables, even though they share `Base`.
from app.persistence.db import tables  # noqa: F401
from app.persistence.db.base import Base
from app.persistence.db.engine import get_database_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `Base.metadata` (app.persistence.db.base) is the single source of truth
# for autogenerate -- every table in app.persistence.db.tables shares it.
target_metadata = Base.metadata

# The connection URL comes from `RESUMEPILOT_DATABASE_URL` (via
# `Settings`/`get_database_url`), never from a literal value checked into
# `alembic.ini` -- `alembic.ini`'s own `sqlalchemy.url` is left as the
# placeholder Alembic generated, and is never read. Deliberately `Settings()`
# here, not the app's cached `get_settings()`: a migration run is a
# one-off CLI invocation, not the long-lived app process that cache exists
# for, and using the cache here would let an unrelated earlier `get_settings()`
# call (e.g. from a test importing `app.app`) freeze in a stale/absent
# `database_url` for the lifetime of the process.
config.set_main_option("sqlalchemy.url", get_database_url(Settings()))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
