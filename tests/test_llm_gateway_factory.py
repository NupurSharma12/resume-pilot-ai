"""Unit tests for `build_llm_gateway` — where provider-chain configuration is interpreted."""

import pytest

from app.core.config import Settings
from app.gateways.llm.chain import GatewayChain
from app.gateways.llm.factory import build_llm_gateway
from app.gateways.llm.gemini_gateway import GeminiGateway
from app.gateways.llm.mock_gateway import MockGateway
from app.gateways.llm.openrouter_gateway import OpenRouterGateway


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
