from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.request_context import RequestContextMiddleware
from app.gateways.llm.factory import build_llm_gateway
from app.persistence.factory import build_persistence_store
from app.persistence.lifecycle import Disposable
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
    # `Disposable` is a structural (runtime_checkable) check, not an
    # isinstance check against `PostgresPersistenceStore` -- this stays
    # correct for whichever backend is configured without this module
    # ever importing a database-specific type (see
    # `app.persistence.lifecycle`'s docstring). `InMemoryPersistenceStore`
    # has nothing to dispose and simply doesn't satisfy `Disposable`.
    persistence_store = app.state.persistence_store
    if isinstance(persistence_store, Disposable):
        await persistence_store.dispose()
        logger.info("persistence_store_disposed")
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
        expose_headers=["Content-Disposition", "X-Export-Fidelity", "X-Request-ID"],
    )
    # Added last so it's the outermost middleware layer (Starlette wraps
    # each `add_middleware` call around the previous stack) -- every
    # request, including CORS preflight, gets a request_id bound into
    # structlog context before anything else runs, and it stays bound for
    # everything that happens further in, including this CORS layer's own
    # processing. See `RequestContextMiddleware`'s docstring for why an
    # unexpected exception is only logged here, never swallowed or
    # reshaped -- Starlette's own `ServerErrorMiddleware`, always outside
    # every user middleware, still produces the existing default 500
    # response untouched.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router)

    return app


app = create_app()
