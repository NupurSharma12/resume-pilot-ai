"""History/resumability, end-to-end, against a real PostgreSQL database.

Unlike `test_job_preparation_history_api.py` (fast, `InMemoryPersistenceStore`,
one fresh store per test), this module builds the real app configured with
`persistence_backend="postgres"` against `RESUMEPILOT_TEST_DATABASE_URL` --
the same opt-in, disposable-database mechanism every other PostgreSQL-only
test in this project already uses (see `tests/persistence_db_support.py`).
Skipped cleanly when that variable is unset.

Deliberately creates and uses exactly **one** persistent job preparation
(see the History Test Isolation & Delete design review's "we should be
able to maintain one explicit test preparation in the database"
requirement) -- one test function, one preparation, walking it through
create -> appears in History -> opened for resumability -> deleted ->
disappears from History -> still addressable by id, in sequence. Kept as
a single `async def test_...` (not one fixture-shared client across
several tests) deliberately: `asyncio_mode = "auto"`'s default fixture
loop scope is per-function, so a module-scoped async client/engine would
outlive the event loop each individual test runs on and fail cross-loop
(confirmed while writing this test) -- one function sidesteps that
entirely, with no project-wide pytest-asyncio config change required.

The LLM gateway is faked (`_FakeGateway`, mirroring `test_analyze_api.py`'s
own), so this exercises real persistence/HTTP wiring without a real,
costly LLM call -- the same reasoning that keeps this out of a live-LLM
Playwright spec (golden-path.spec.ts/downloads.spec.ts already cover that
separately, and now tag their own preparations `X-E2E-Test: true` so they
never appear in History at all -- see
`frontend/e2e/helpers/tailoringFlow.ts`).

By the end of this test, the one preparation it created is soft-deleted --
not physically removed (see `JobPreparation.deleted_at`'s docstring), but
no longer visible in `list_job_preparations`, so repeated runs against the
same disposable database never accumulate visible History clutter.
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
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow
from tests.persistence_db_support import (
    TEST_DATABASE_URL,
    downgrade_test_database,
    upgrade_test_database,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "RESUMEPILOT_TEST_DATABASE_URL is not set -- skipping the real-PostgreSQL "
        "History/resumability end-to-end test."
    ),
)

_RESULT = ResumeAnalysisResult(
    overall_assessment=OverallAssessment(
        overall_score=78,
        hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
        summary="Solid fit overall.",
    ),
    skill_matches=[],
    matching_projects=[],
    strengths=["Real Postgres History test preparation."],
    weaknesses=[],
    resume_improvements=[],
)


class _FakeGateway:
    provider_name = "fake"
    supports_structured_output = True

    async def generate_structured(self, request: LLMRequest, response_model):
        return _RESULT

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def stream(self, request: LLMRequest):
        raise NotImplementedError
        yield  # pragma: no cover


@pytest.fixture(scope="module", autouse=True)
def _postgres_schema_for_this_suite():
    """Migrate `RESUMEPILOT_TEST_DATABASE_URL` to `head` once for this whole module.

    Mirrors `test_persistence_contract.py`'s identically named fixture --
    see that module for why this is a no-op when the variable is unset.
    """
    if not TEST_DATABASE_URL:
        yield
        return

    upgrade_test_database()
    yield
    downgrade_test_database()


async def test_one_persistent_preparation_through_history_create_view_and_delete() -> None:
    assert (
        TEST_DATABASE_URL is not None
    )  # narrows for type-checkers; skipif already guarantees this
    settings = Settings(
        log_json=False,
        gemini_api_key="test-gemini-api-key",
        persistence_backend="postgres",
        database_url=TEST_DATABASE_URL,
    )
    app = create_app(settings)
    app.dependency_overrides[get_resume_analysis_workflow] = lambda: ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=_FakeGateway(),
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resume_text = "SUMMARY\nReal Postgres History E2E test resume."
            job_description = "History/resumability real-Postgres end-to-end test JD."

            # 1. Create the one persistent test preparation -- a real,
            # History-visible (include_in_history defaults True) analysis,
            # durably written to the real database via the real endpoint.
            create_response = await client.post(
                "/v1/analyze",
                json={"resume": resume_text, "job_description": job_description},
            )
            assert create_response.status_code == 200
            job_preparation_id = create_response.json()["job_preparation_id"]
            assert job_preparation_id is not None

            # 2. It appears in History.
            list_response = await client.get("/v1/job-preparations")
            assert job_preparation_id in [item["id"] for item in list_response.json()["items"]]

            # 3. Continue works -- the backend half of resumability: the
            # full detail a frontend rehydrates from.
            # `ResumeSessionContext.rehydrateFromHistory`'s own mapping
            # from this exact response shape is covered by
            # `frontend/src/session/rehydrateFromJobPreparation.test.ts`;
            # this proves the real, Postgres-backed response actually has
            # everything that mapper needs, not a mocked stand-in.
            detail_response = await client.get(f"/v1/job-preparations/{job_preparation_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["resume_text"] == resume_text
            assert detail["job_description"] == job_description
            assert detail["analysis_result"]["overall_assessment"]["overall_score"] == 78
            assert detail["checkpoints"]["initial_analysis_completed_at"] is not None

            # 4. It can be deleted.
            delete_response = await client.delete(f"/v1/job-preparations/{job_preparation_id}")
            assert delete_response.status_code == 204

            # 5. It disappears from History afterward.
            list_after_delete = await client.get("/v1/job-preparations")
            assert job_preparation_id not in [
                item["id"] for item in list_after_delete.json()["items"]
            ]

            # 6. Chosen soft-delete behavior, confirmed end to end: gone
            # from the list, but still addressable directly by id.
            reread_response = await client.get(f"/v1/job-preparations/{job_preparation_id}")
            assert reread_response.status_code == 200
            assert reread_response.json()["id"] == job_preparation_id
            UUID(job_preparation_id)  # sanity: still a well-formed id, nothing corrupted
    finally:
        await app.state.persistence_store.dispose()
