"""Unit tests for `get_database_url` -- no database connection involved."""

import pytest

from app.core.config import Settings
from app.persistence.db.engine import get_database_url


def test_returns_the_configured_url() -> None:
    settings = Settings(database_url="postgresql+asyncpg://user:pw@host/db")

    assert get_database_url(settings) == "postgresql+asyncpg://user:pw@host/db"


def test_raises_when_unset() -> None:
    settings = Settings(database_url=None)

    with pytest.raises(ValueError, match="RESUMEPILOT_DATABASE_URL is required"):
        get_database_url(settings)


def test_default_settings_leave_database_url_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """The field's true default is unset -- independent of any developer's local `.env`.

    `Settings` always reads `.env` (see `Settings.model_config`'s
    `env_file=".env"`), so a bare `Settings()` here would otherwise reflect
    whatever `RESUMEPILOT_DATABASE_URL` a developer's own `.env` happens to
    set for local Postgres testing (see docs/persistent-backend-workflow-state.md) --
    not this field's actual default. `_env_file=None` bypasses `.env`
    loading for this instantiation only; `monkeypatch.delenv` covers the
    same variable if it's exported directly in the shell instead. Together
    they isolate this assertion from the developer's environment entirely,
    matching what `test_raises_when_unset` above already assumes by
    passing `database_url=None` explicitly.
    """
    monkeypatch.delenv("RESUMEPILOT_DATABASE_URL", raising=False)

    assert Settings(_env_file=None).database_url is None
