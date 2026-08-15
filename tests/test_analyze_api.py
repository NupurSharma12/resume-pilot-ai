"""Integration tests for `POST /v1/analyze`'s Phase 3 persistence wiring.

Builds its own app instance per test (rather than the shared `client`
fixture) so `get_resume_analysis_workflow` can be overridden with a
`FakeGateway`-backed workflow, and `get_persistence_store` overridden with
a fresh, inspectable `InMemoryPersistenceStore` -- the same
dependency-override pattern `test_career_conversation_api.py`/
`test_tailoring_suggestions_api.py` already use, applied here for the
first time to `/v1/analyze` (this endpoint had no dedicated API-level
test file before Phase 3).
"""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.analyze import get_resume_analysis_workflow
from app.app import create_app
from app.core.config import Settings
from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
)
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.models import ResumeVersionSource
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow

_RESULT = ResumeAnalysisResult(
    overall_assessment=OverallAssessment(
        overall_score=70,
        hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
        summary="Solid fit overall.",
    ),
    skill_matches=[],
    matching_projects=[],
    strengths=["Strong backend ownership."],
    weaknesses=["Frontend experience is unclear."],
    resume_improvements=[],
)


class _FakeGateway:
    """Minimal `LLMGateway`: always returns the same fixed `ResumeAnalysisResult`."""

    provider_name = "fake"
    supports_structured_output = True

    async def generate_structured(self, request: LLMRequest, response_model):
        return _RESULT

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, request: LLMRequest):
        raise NotImplementedError
        yield  # pragma: no cover


@pytest.fixture
async def api_client_factory():
    """Return a factory building a fresh `(client, persistence_store)` per test."""
    clients: list[AsyncClient] = []

    async def _factory() -> tuple[AsyncClient, InMemoryPersistenceStore]:
        settings = Settings(
            log_json=False, gemini_api_key="test-gemini-api-key", persistence_backend="memory"
        )
        app = create_app(settings)
        app.dependency_overrides[get_resume_analysis_workflow] = lambda: ResumeAnalysisWorkflow(
            prompt_builder=ResumeAnalysisPromptBuilder(),
            gateway=_FakeGateway(),
        )
        # Real Phase 3 wiring (app.persistence.dependencies.get_persistence_store)
        # is left un-overridden -- this asserts against the *actual*
        # `app.state.persistence_store` the app itself constructed, not a
        # stand-in, since that's the wiring under test here.
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client, app.state.persistence_store

    yield _factory

    for client in clients:
        await client.aclose()


async def test_analyze_creates_a_resume_and_original_upload_version(api_client_factory) -> None:
    client, store = await api_client_factory()

    response = await client.post(
        "/v1/analyze", json={"resume": "Backend engineer resume.", "job_description": "JD text."}
    )

    assert response.status_code == 200
    body = response.json()
    job_preparation_id = body["job_preparation_id"]
    assert job_preparation_id is not None

    job_preparation = await store.get_job_preparation(UUID(job_preparation_id))
    assert job_preparation is not None
    assert job_preparation.analysis_result["overall_assessment"]["overall_score"] == 70
    assert job_preparation.status == "active"

    source_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    assert source_version.version_number == 1
    assert source_version.source == ResumeVersionSource.ORIGINAL_UPLOAD
    assert source_version.content == "Backend engineer resume."


async def test_two_unrelated_analyze_calls_never_merge_into_one_resume(api_client_factory) -> None:
    client, store = await api_client_factory()

    first_response = await client.post(
        "/v1/analyze", json={"resume": "Resume A text.", "job_description": "JD A."}
    )
    second_response = await client.post(
        "/v1/analyze", json={"resume": "Resume B text.", "job_description": "JD B."}
    )

    first_preparation = await store.get_job_preparation(
        UUID(first_response.json()["job_preparation_id"])
    )
    second_preparation = await store.get_job_preparation(
        UUID(second_response.json()["job_preparation_id"])
    )

    first_version = await store.get_resume_version(first_preparation.source_resume_version_id)
    second_version = await store.get_resume_version(second_preparation.source_resume_version_id)

    assert first_version.resume_id != second_version.resume_id


async def test_repeated_analyze_of_the_same_resume_still_creates_a_second_resume(
    api_client_factory,
) -> None:
    """No client/session identity exists at this layer -- see the Phase 3 report's idempotency note.

    Two calls with byte-identical resume text are two separate uploads as
    far as this endpoint knows -- this is the documented, deliberate
    absence of a retry/idempotency mechanism, not a bug.
    """
    client, store = await api_client_factory()
    payload = {"resume": "Identical resume text.", "job_description": "Identical JD."}

    first_response = await client.post("/v1/analyze", json=payload)
    second_response = await client.post("/v1/analyze", json=payload)

    assert (
        first_response.json()["job_preparation_id"] != second_response.json()["job_preparation_id"]
    )


async def test_analyze_without_the_e2e_test_header_includes_the_preparation_in_history(
    api_client_factory,
) -> None:
    """The safe default: a request with no `X-E2E-Test` header behaves exactly as before."""
    client, store = await api_client_factory()

    response = await client.post(
        "/v1/analyze", json={"resume": "Backend engineer resume.", "job_description": "JD text."}
    )

    job_preparation = await store.get_job_preparation(UUID(response.json()["job_preparation_id"]))
    assert job_preparation.include_in_history is True


async def test_analyze_with_the_e2e_test_header_excludes_the_preparation_from_history(
    api_client_factory,
) -> None:
    """`X-E2E-Test: true` is the only way to opt a preparation out of History.

    The preparation is still fully created and persisted, usable by id
    like any other -- only `include_in_history` differs.
    """
    client, store = await api_client_factory()

    response = await client.post(
        "/v1/analyze",
        json={"resume": "Backend engineer resume.", "job_description": "JD text."},
        headers={"X-E2E-Test": "true"},
    )

    job_preparation_id = UUID(response.json()["job_preparation_id"])
    job_preparation = await store.get_job_preparation(job_preparation_id)
    assert job_preparation.include_in_history is False
    assert await store.list_job_preparations() == []
    assert job_preparation.analysis_result is not None
