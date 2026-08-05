"""Builds the configured `LLMGateway` (a `GatewayChain`) from `Settings`.

The single place that maps environment configuration
(`RESUMEPILOT_PRIMARY_PROVIDER` / `_SECONDARY_PROVIDER` / `_TERTIARY_PROVIDER`)
onto concrete gateway instances, wired into a `GatewayChain`. Every FastAPI
dependency-provider function that previously constructed a gateway inline
from `settings.llm_provider` (see `analyze.py`/`career_conversation.py`)
now calls `build_llm_gateway` instead — so introducing a new provider, or
reordering the fallback chain, is a one-place change every current and
future workflow automatically picks up, per the Multi-LLM Resilience
sprint's explicit goal.
"""

from app.core.config import Settings
from app.core.logging import get_logger
from app.gateways.llm.chain import GatewayChain
from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.gemini_gateway import GeminiGateway
from app.gateways.llm.mock_gateway import MockGateway
from app.gateways.llm.openrouter_gateway import OpenRouterGateway

logger = get_logger(__name__)

_BUILDERS = {
    "gemini": GeminiGateway,
    "openrouter": OpenRouterGateway,
    "mock": lambda settings: MockGateway(),
}


def _build_gateway(provider: str, settings: Settings) -> LLMGateway:
    """Construct one concrete gateway by name.

    Unrecognized provider names raise `ValueError` immediately rather
    than being silently skipped — the same fail-fast reasoning
    `get_resume_analysis_workflow` already used for an unrecognized
    `llm_provider`: a typo in `RESUMEPILOT_PRIMARY_PROVIDER` should be
    impossible to miss, not quietly reduce the chain to fewer providers
    than intended.
    """
    builder = _BUILDERS.get(provider)
    if builder is None:
        logger.error("unknown_llm_provider", provider=provider)
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {sorted(_BUILDERS)}.")
    return builder(settings)


def build_llm_gateway(settings: Settings) -> LLMGateway:
    """Build the provider chain configured by primary/secondary/tertiary provider settings.

    `primary_provider` is always present (it has a default); `secondary_
    provider`/`tertiary_provider` are optional (`None` unless set) — a
    chain of just one provider is valid, e.g. a minimal local setup that
    only ever wants `"mock"`. Order in the resulting chain is exactly
    primary, then secondary (if set), then tertiary (if set); there is
    currently no way to configure more than three tiers, matching the
    sprint's explicit example.

    A new chain (and new gateway instances) is built on every call rather
    than cached, mirroring `get_resume_analysis_workflow`'s existing
    per-request construction of a single gateway: every gateway here is
    cheap and stateless to construct (an HTTP/SDK client, no warm-up), so
    there's no cost or correctness reason to share instances across
    requests, and per-call construction keeps this function simple and
    means a config change takes effect on the very next request.

    A provider named here but missing its required credentials (e.g.
    `"openrouter"` in the chain with no `RESUMEPILOT_OPENROUTER_API_KEY`)
    is never silently dropped from the chain — `_build_gateway` raises
    `ValueError` immediately (via the concrete gateway's own `__init__`;
    see `GeminiGateway`/`OpenRouterGateway`), which propagates straight
    out of this function uncaught. `app.py`'s `lifespan` calls this
    function once at process startup specifically so that kind of
    misconfiguration fails the app at boot, not on whichever request
    happens to need the gateway first.

    Logs `llm_provider_chain_configured` with the resolved `providers`
    list (e.g. `["gemini", "openrouter", "mock"]`) every time a chain is
    built — this is what makes "which providers is this process actually
    using" directly visible in the logs, including from the startup call
    above, instead of only being inferable from `.env`.
    """
    configured_providers = (
        settings.primary_provider,
        settings.secondary_provider,
        settings.tertiary_provider,
    )
    provider_names = [provider for provider in configured_providers if provider]
    gateways = [_build_gateway(provider, settings) for provider in provider_names]
    logger.info("llm_provider_chain_configured", providers=provider_names)
    return GatewayChain(gateways)
