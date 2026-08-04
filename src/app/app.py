from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.gateways.llm.factory import build_llm_gateway
from app.sessions.conversation_session import ConversationSessionStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger = get_logger(__name__)
    logger.info("app_startup", environment=app.state.settings.environment)
    # Constructed and immediately discarded: this call's only purpose is
    # to fail the app at startup (not on whichever request happens to
    # need it first) if a provider named in RESUMEPILOT_*_PROVIDER is
    # missing its required credentials, and to emit
    # "llm_provider_chain_configured" once at boot, showing exactly which
    # providers this process resolved from its environment (see
    # gateways/llm/factory.py's docstring). Every request still builds
    # its own gateway chain via the same function — this doesn't cache or
    # share the chain across requests.
    build_llm_gateway(app.state.settings)
    yield
    logger.info("app_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory: builds a fully configured FastAPI instance."""
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Process-lifetime singleton, unlike everything else attached to
    # `app.state`: Career Conversation sessions must persist across the
    # start -> answer -> answer -> ... request sequence, so this store is
    # constructed once here rather than per-request (see
    # `app.sessions.conversation_session`'s module docstring).
    app.state.conversation_session_store = ConversationSessionStore()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()
