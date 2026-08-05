"""Tests for `app.py`'s `lifespan` — startup-time provider-chain validation and logging.

Calls `lifespan(app)` directly as an async context manager rather than
spinning up a real ASGI server: `lifespan` only reads `app.state.settings`
(already set by `create_app`) and calls `build_llm_gateway`, so entering it
directly exercises exactly the code path a real server's startup event
would, without needing a running server or an ASGI client configured for
lifespan events (the shared `client`/`api_client_factory` fixtures
elsewhere in this suite deliberately don't trigger lifespan at all).

Log assertions monkeypatch the loggers directly rather than asserting on
rendered output (`structlog.testing.capture_logs()` or captured stdout):
this suite calls `configure_logging` (via `create_app`) many times across
many files, and `cache_logger_on_first_use=True` (set by
`configure_logging`) freezes `gateways/llm/factory.py`'s module-level
logger to whichever processors were active the *first* time it was ever
used anywhere in the process — long since true by the time these tests
run, from an earlier test's call to `build_llm_gateway`. Replacing the
logger objects themselves sidesteps that fragility entirely.
"""

import pytest

from app.app import create_app, lifespan
from app.core.config import Settings


class _RecordingLogger:
    """See `test_llm_gateway_factory.py`'s identical helper for why this exists."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})

    def error(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})


async def test_lifespan_succeeds_and_logs_provider_chain_for_valid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_logger = _RecordingLogger()
    monkeypatch.setattr("app.gateways.llm.factory.logger", fake_logger)
    # `lifespan` creates its own logger fresh, at call time, via
    # `get_logger(__name__)` — patching the factory function itself (not
    # a specific module attribute) is what reaches that call.
    monkeypatch.setattr("app.app.get_logger", lambda *_args, **_kwargs: fake_logger)

    settings = Settings(
        primary_provider="gemini",
        secondary_provider="openrouter",
        tertiary_provider="mock",
        gemini_api_key="test-key",
        openrouter_api_key="test-key",
    )
    app = create_app(settings)

    async with lifespan(app):
        pass

    configured = [c for c in fake_logger.calls if c["event"] == "llm_provider_chain_configured"]
    assert len(configured) == 1
    assert configured[0]["providers"] == ["gemini", "openrouter", "mock"]

    assert any(c["event"] == "app_startup" for c in fake_logger.calls)
    assert any(c["event"] == "app_shutdown" for c in fake_logger.calls)


async def test_lifespan_fails_fast_when_configured_provider_has_no_api_key() -> None:
    """The app must refuse to start, not silently drop the misconfigured provider."""
    settings = Settings(
        primary_provider="gemini",
        secondary_provider="openrouter",
        tertiary_provider="mock",
        gemini_api_key="test-key",
        openrouter_api_key=None,
    )
    app = create_app(settings)

    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        async with lifespan(app):
            pass


async def test_lifespan_fails_fast_for_unknown_provider_name() -> None:
    settings = Settings(primary_provider="not-a-real-provider")
    app = create_app(settings)

    with pytest.raises(ValueError, match="Unknown provider"):
        async with lifespan(app):
            pass
