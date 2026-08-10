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

    # Persistence backend (Configurable Persistence): `build_persistence_store`
    # (persistence/factory.py) reads this to decide which `PersistenceStore`
    # implementation to construct. `memory` is the default so a fresh clone
    # runs with zero database configuration; `postgres` constructs a
    # `PostgresPersistenceStore` (persistence/postgres_store.py), requiring
    # `database_url` below. Neither workflows nor API endpoints read from
    # either store yet (see docs/persistent-backend-workflow-state.md) --
    # that wiring is a later milestone.
    persistence_backend: Literal["memory", "postgres"] = Field(
        default="memory",
        description=(
            "Which PersistenceStore implementation to use. 'memory' (the default) requires "
            "no configuration and does not survive a process restart. 'postgres' persists "
            "durably via PostgreSQL/Neon and requires database_url below."
        ),
    )
    database_url: str | None = Field(
        default=None,
        description=(
            "SQLAlchemy async connection URL for PostgreSQL, e.g. "
            "'postgresql+asyncpg://user:password@host/dbname?ssl=require'. Only required when "
            "persistence_backend='postgres' (see persistence/db/engine.py's get_database_url) "
            "or when running Alembic migrations against a real database -- unused and safe to "
            "leave unset under the default 'memory' backend. Never commit a real value; set it "
            "via the environment or a local, gitignored .env."
        ),
    )

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
    openrouter_models: list[str] = Field(
        default_factory=lambda: [
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        description=(
            "Ordered list of OpenRouter model identifiers to try, free models by default. "
            "Verified against https://openrouter.ai/api/v1/models as currently valid "
            "':free'-suffixed ids on 2026-08-09 — the previous defaults (Qwen/Llama/DeepSeek "
            "entries) had all lost their free tier by then and were 404ing on every call. "
            "OpenRouterGateway attempts them in order on every call, falling back to the "
            "next one on a timeout, HTTP 429, HTTP 404, HTTP 5xx, an empty response, "
            "malformed JSON, or a schema-validation failure (see OpenRouterGateway's module "
            "docstring) — only once every model in this list has failed does the "
            "'openrouter' leg of the provider chain itself fail, letting GatewayChain fall "
            "back to the next configured provider. Does NOT retry across models on an "
            "authentication failure, a bad request, or an invalid API key (HTTP "
            "401/403/400): those fail identically against every model, so the first one "
            "fails fast instead of burning through the rest of the list. HTTP 404 is "
            "retried, not failed fast — see OpenRouterGateway's `_RETRYABLE_STATUS_CODES` "
            "comment for why, since it covers both a retired model id and OpenRouter's own "
            "transient 'no provider currently serving this free model' condition. Keeping "
            "this list current is still worthwhile even so: a dead first entry still costs "
            "one wasted round trip before falling through to the next model. If every model "
            "here starts 404ing, check https://openrouter.ai/api/v1/models for current "
            "':free'-suffixed replacements. Avoid *reasoning* models (e.g. "
            "openai/gpt-oss-20b:free): one was observed, under this app's long "
            "structured-output prompts, returning finish_reason=stop with an empty/null "
            "message.content — exactly the failure mode this list-based fallback exists to "
            "route around, but still wasted latency on every call if it's first in the list."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so env parsing happens once per process."""
    return Settings()
