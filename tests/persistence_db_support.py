"""Shared PostgreSQL test-database support.

Centralizes "how do I point Alembic at a real, disposable PostgreSQL
database for testing" in one place, reused by both
`test_persistence_db_migration_integration.py` (Phase 1) and
`test_persistence_contract.py`/`test_persistence_postgres_integration.py`
(Phase 2) -- per this project's explicit preference for reusing Phase 1's
existing opt-in database-test mechanism rather than building a second one.

Not named `test_*.py`, so pytest never collects this module itself.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

# Deliberately distinct from the application's own `RESUMEPILOT_DATABASE_URL`
# (see `app.core.config.Settings.database_url`): this is a test-only opt-in,
# so running the ordinary suite can never accidentally reach a real (e.g.
# Neon) database a developer happens to have configured for the app itself.
TEST_DATABASE_URL = os.environ.get("RESUMEPILOT_TEST_DATABASE_URL")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    return Config(str(_REPO_ROOT / "alembic.ini"))


@contextmanager
def _database_url_env() -> Iterator[None]:
    """Point `RESUMEPILOT_DATABASE_URL` at `TEST_DATABASE_URL`, only for this block.

    Scoped as tightly as possible around the one Alembic call that
    actually needs it (`migrations/env.py` reads it via a fresh
    `Settings()` at invocation time) -- never held open for a whole test
    or session, which would leak a real-looking `RESUMEPILOT_DATABASE_URL`
    into any other test that happens to run while it's set (e.g. one
    asserting `Settings().database_url` is `None` by default).
    """
    previous = os.environ.get("RESUMEPILOT_DATABASE_URL")
    os.environ["RESUMEPILOT_DATABASE_URL"] = TEST_DATABASE_URL or ""
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("RESUMEPILOT_DATABASE_URL", None)
        else:
            os.environ["RESUMEPILOT_DATABASE_URL"] = previous


def upgrade_test_database() -> None:
    """Run `alembic upgrade head` against `TEST_DATABASE_URL`."""
    with _database_url_env():
        command.upgrade(alembic_config(), "head")


def downgrade_test_database() -> None:
    """Run `alembic downgrade base` against `TEST_DATABASE_URL`."""
    with _database_url_env():
        command.downgrade(alembic_config(), "base")


def check_test_database() -> None:
    """Run `alembic check` (autogenerate diff) against `TEST_DATABASE_URL`."""
    with _database_url_env():
        command.check(alembic_config())
