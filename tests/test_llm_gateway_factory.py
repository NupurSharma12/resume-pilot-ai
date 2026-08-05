"""Unit tests for `build_llm_gateway` — where provider-chain configuration is interpreted."""

import pytest

from app.core.config import Settings
from app.gateways.llm.chain import GatewayChain
from app.gateways.llm.factory import build_llm_gateway
from app.gateways.llm.gemini_gateway import GeminiGateway
from app.gateways.llm.mock_gateway import MockGateway
from app.gateways.llm.openrouter_gateway import OpenRouterGateway


class _RecordingLogger:
    """A minimal stand-in for `factory.py`'s module-level structlog logger.

    Monkeypatched in directly, rather than asserting on rendered log
    output: `structlog`'s `cache_logger_on_first_use=True` (set by
    `configure_logging`, which many other tests in this suite call via
    `create_app`) freezes a module-level logger to whichever processors
    were active the *first* time it was ever used in the process — by the
    time these tests run, that's long since happened via an earlier
    test's call to `build_llm_gateway`, so neither
    `structlog.testing.capture_logs()` nor capturing real stdout reaches
    it reliably. Replacing the logger object itself sidesteps that
    entirely and asserts on exactly what matters: that `build_llm_gateway`
    calls `.info("llm_provider_chain_configured", providers=[...])`.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})

    def error(self, event: str, **kwargs: object) -> None:
        self.calls.append({"event": event, **kwargs})


def test_single_provider_chain() -> None:
    # secondary/tertiary explicitly None here (not just omitted): this
    # repo's own .env sets RESUMEPILOT_SECONDARY_PROVIDER, and pydantic-
    # settings falls back to reading it for any field not passed
    # explicitly to Settings() — this test wants a genuinely single-tier
    # chain regardless of what's in .env.
    settings = Settings(primary_provider="mock", secondary_provider=None, tertiary_provider=None)
    gateway = build_llm_gateway(settings)

    assert isinstance(gateway, GatewayChain)
    assert gateway.provider_name == "chain[mock]"


def test_three_tier_chain_in_order() -> None:
    settings = Settings(
        primary_provider="gemini",
        secondary_provider="openrouter",
        tertiary_provider="mock",
        gemini_api_key="test-key",
        openrouter_api_key="test-key",
    )
    gateway = build_llm_gateway(settings)

    assert isinstance(gateway, GatewayChain)
    assert gateway.provider_name == "chain[gemini,openrouter,mock]"
    # `_gateways` is a private implementation detail, but asserting the
    # concrete types landed in the right order is the only way to verify
    # `build_llm_gateway` actually constructed the right classes, not just
    # gateways that happen to report the right names.
    types_in_order = [type(g) for g in gateway._gateways]
    assert types_in_order == [GeminiGateway, OpenRouterGateway, MockGateway]


def test_secondary_and_tertiary_are_optional() -> None:
    settings = Settings(primary_provider="mock", secondary_provider=None, tertiary_provider=None)
    gateway = build_llm_gateway(settings)

    assert gateway.provider_name == "chain[mock]"


def test_unknown_provider_name_raises() -> None:
    settings = Settings(primary_provider="not-a-real-provider")
    with pytest.raises(ValueError, match="Unknown provider"):
        build_llm_gateway(settings)


def test_gemini_without_api_key_raises_when_selected() -> None:
    settings = Settings(primary_provider="gemini", gemini_api_key=None)
    with pytest.raises(ValueError, match="gemini_api_key is required"):
        build_llm_gateway(settings)


def test_openrouter_without_api_key_raises_when_selected() -> None:
    settings = Settings(primary_provider="openrouter", openrouter_api_key=None)
    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        build_llm_gateway(settings)


def test_openrouter_missing_key_fails_fast_even_as_secondary() -> None:
    """A provider configured further down the chain still fails fast, not just when primary.

    Regression coverage for the exact reported symptom: OpenRouter named
    as a fallback tier, but with no API key, must never be silently
    dropped from the chain -- it should be impossible for the chain to
    quietly end up as just `[gemini, mock]` because the middle provider
    "didn't work out". `_build_gateway` constructs providers eagerly, in
    order, so a missing key on any of them raises before `GatewayChain`
    is ever constructed.
    """
    settings = Settings(
        primary_provider="gemini",
        secondary_provider="openrouter",
        tertiary_provider="mock",
        gemini_api_key="test-key",
        openrouter_api_key=None,
    )
    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        build_llm_gateway(settings)


def test_build_logs_the_resolved_provider_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_logger = _RecordingLogger()
    monkeypatch.setattr("app.gateways.llm.factory.logger", fake_logger)
    settings = Settings(
        primary_provider="gemini",
        secondary_provider="openrouter",
        tertiary_provider="mock",
        gemini_api_key="test-key",
        openrouter_api_key="test-key",
    )

    build_llm_gateway(settings)

    configured = [c for c in fake_logger.calls if c["event"] == "llm_provider_chain_configured"]
    assert len(configured) == 1
    assert configured[0]["providers"] == ["gemini", "openrouter", "mock"]


def test_build_logs_only_the_configured_tiers_when_secondary_is_not_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The historical misconfiguration this bug was reported against: secondary left as "mock".

    Not a code bug -- `build_llm_gateway` correctly reflects exactly what
    it was told to build. This test documents that a chain configured as
    gemini/mock genuinely never includes OpenRouter, so the log this
    sprint added is what would have made that immediately visible.
    """
    fake_logger = _RecordingLogger()
    monkeypatch.setattr("app.gateways.llm.factory.logger", fake_logger)
    settings = Settings(
        primary_provider="gemini",
        secondary_provider="mock",
        tertiary_provider=None,
        gemini_api_key="test-key",
    )

    gateway = build_llm_gateway(settings)

    assert gateway.provider_name == "chain[gemini,mock]"
    configured = [c for c in fake_logger.calls if c["event"] == "llm_provider_chain_configured"]
    assert configured[0]["providers"] == ["gemini", "mock"]
    assert "openrouter" not in configured[0]["providers"]
