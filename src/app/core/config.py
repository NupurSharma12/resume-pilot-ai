from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RESUMEPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ResumePilot AI"
    environment: Literal["local", "development", "staging", "production"] = "local"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Provider chain (Multi-LLM Resilience): `build_llm_gateway`
    # (gateways/llm/factory.py) wires these into an ordered `GatewayChain`
    # — primary is tried first, falling back to secondary then tertiary
    # only on a transient failure (rate limit, timeout, 5xx). Left as
    # plain `str`/`str | None` rather than a `Literal`, for the same
    # reason the old `llm_provider` field was: an unrecognized name should
    # surface as an explicit `ValueError` from `build_llm_gateway` at
    # request time, not a settings-load-time validation error.
    primary_provider: str = Field(
        default="gemini",
        description="The first provider every call is attempted against.",
    )
    secondary_provider: str | None = Field(
        default=None,
        description="Fallback provider, tried only if the primary fails transiently.",
    )
    tertiary_provider: str | None = Field(
        default=None,
        description=(
            "Second fallback provider, tried only if primary and secondary both fail transiently."
        ),
    )

    gemini_api_key: str | None = Field(
        default=None,
        description=(
            "API key for the Gemini provider. Optional at the settings level — only required "
            "if 'gemini' actually appears in the provider chain; see GeminiGateway.__init__."
        ),
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash", description="Default Gemini model identifier to use."
    )

    openrouter_api_key: str | None = Field(
        default=None,
        description=(
            "API key for the OpenRouter provider. Optional at the settings level — only "
            "required if 'openrouter' actually appears in the provider chain; see "
            "OpenRouterGateway.__init__."
        ),
    )
    openrouter_model: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free",
        description="OpenRouter model identifier to use — a free model by default.",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so env parsing happens once per process."""
    return Settings()
