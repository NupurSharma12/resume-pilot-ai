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


def test_default_settings_leave_database_url_unset() -> None:
    assert Settings().database_url is None
