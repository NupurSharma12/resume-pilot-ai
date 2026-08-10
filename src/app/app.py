from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.gateways.llm.factory import build_llm_gateway
from app.persistence.factory import build_persistence_store
from app.sessions.conversation_session import ConversationSessionStore
from app.sessions.tailoring_plan_store import TailoringPlanStore


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
    # Same process-lifetime-singleton reasoning as `conversation_session_store`
    # above: generated suggestion plans must persist across the
    # generate -> apply -> export request sequence (see
    # `app.sessions.tailoring_plan_store`'s module docstring).
    app.state.tailoring_plan_store = TailoringPlanStore()
    # Durable product history (Resume/ResumeVersion/JobPreparation) --
    # distinct from the two transient stores above, which only ever hold
    # in-flight workflow-sequencing state. Implementation is chosen by
    # `settings.persistence_backend` (see `build_persistence_store`);
    # `memory` (the default) is itself still process-lifetime-only, same
    # as the stores above, until the `postgres` backend exists.
    app.state.persistence_store = build_persistence_store(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Browsers only expose a small safelisted set of response headers
        # to cross-origin JS by default (Content-Type, Content-Length,
        # ...) -- Content-Disposition and X-Export-Fidelity aren't in it,
        # so without this, `POST /tailoring-suggestions/{plan_id}/export`
        # would work fine over the wire but the frontend's `fetch()` would
        # get `null` back from `response.headers.get(...)` for both,
        # silently breaking filename/fidelity parsing (see
        # `frontend/src/lib/tailoringSuggestionsApi.ts`).
        expose_headers=["Content-Disposition", "X-Export-Fidelity"],
    )

    app.include_router(api_router)

    return app


app = create_app()
