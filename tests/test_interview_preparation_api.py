"""Integration tests for `POST /v1/job-preparations/{id}/interview-preparation`.

Builds its own app instance per test (matching
`test_job_preparation_history_api.py`'s own convention) so each test gets
a fresh, isolated `InMemoryPersistenceStore`, and overrides
`get_interview_preparation_workflow` with a workflow backed by the
`FakeGateway` from `test_interview_preparation_workflow.py` -- mirroring
`test_tailoring_suggestions_api.py`'s dependency-override pattern, for the
same reason `MockGateway` can't reliably exercise this endpoint's happy
path (see that FakeGateway's docstring).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.interview_preparation import get_interview_preparation_workflow
from app.app import create_app
from app.core.config import Settings
from app.models.interview_preparation import (
    BehavioralQuestion,
    BehavioralQuestionSource,
    CodingQuestion,
    Difficulty,
    GeneratedInterviewPreparation,
    GeneratedTechnicalPreparation,
    InterviewPreparationResult,
    InterviewPreparationStage,
    SystemDesignQuestion,
)
from app.orchestration.job_preparation_persistence import (
    record_applied_tailoring_selection,
    record_career_conversation,
    record_generated_tailoring_plan,
    record_interview_preparation,
    start_job_preparation,
)
from app.persistence.models import JobPreparationStatus
from app.prompts.interview_preparation_prompt_builder import InterviewPreparationPromptBuilder
from app.workflows.interview_preparation_workflow import InterviewPreparationWorkflow
from tests.test_interview_preparation_workflow import FakeGateway

_ANALYSIS = {"overall_assessment": {"overall_score": 70}}


def _generated(additional_behavioral: list[str] | None = None) -> GeneratedInterviewPreparation:
    return GeneratedInterviewPreparation(
        system_design_questions=[
            SystemDesignQuestion(
                question="Design a distributed document-analysis pipeline.",
                rationale="The resume shows large-scale backend systems experience.",
            )
        ],
        coding_questions=[
            CodingQuestion(
                title="Merge Intervals",
                topic="Sorting",
                difficulty=Difficulty.MEDIUM,
                relevance="The role involves scheduling logic.",
            )
        ],
        additional_behavioral_questions=additional_behavioral or [],
    )


@pytest.fixture
async def api_client_factory():
    """Return a factory building a fresh `(client, persistence_store, gateway)` per test."""
    clients: list[AsyncClient] = []

    async def _factory(
        generated: GeneratedInterviewPreparation | GeneratedTechnicalPreparation | BaseException,
    ) -> tuple[AsyncClient, object, FakeGateway]:
        settings = Settings(
            log_json=False, gemini_api_key="test-gemini-api-key", persistence_backend="memory"
        )
        app = create_app(settings)
        gateway = FakeGateway(generated)
        app.dependency_overrides[get_interview_preparation_workflow] = lambda: (
            InterviewPreparationWorkflow(InterviewPreparationPromptBuilder(), gateway)
        )
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client, app.state.persistence_store, gateway

    yield _factory

    for client in clients:
        await client.aclose()


async def test_generate_returns_404_for_an_unknown_job_preparation(api_client_factory) -> None:
    client, _store, _gateway = await api_client_factory(_generated())

    response = await client.post(f"/v1/job-preparations/{uuid4()}/interview-preparation")

    assert response.status_code == 404


async def test_generate_returns_and_persists_the_guide(api_client_factory) -> None:
    client, store, gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    body = response.json()
    assert (
        body["system_design_questions"][0]["question"]
        == "Design a distributed document-analysis pipeline."
    )
    assert body["coding_questions"][0]["title"] == "Merge Intervals"
    assert body["behavioral_questions"] == []
    assert gateway.call_count == 1

    detail = await client.get(f"/v1/job-preparations/{job_preparation.id}")
    assert detail.json()["interview_preparation"] == body


async def test_generate_uses_career_conversation_when_available(api_client_factory) -> None:
    client, store, _gateway = await api_client_factory(
        _generated(additional_behavioral=["Tell me about a recent challenge."])
    )
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    await record_career_conversation(
        store,
        job_preparation.id,
        {
            "session_id": "s-1",
            "status": "complete",
            "history": [
                {
                    "topic": "Leadership",
                    "question": "Describe a time you led a migration.",
                    "answer": "I led a 4-engineer migration off a legacy monolith.",
                    "assistant_response": None,
                }
            ],
            "current_question": None,
            "stop_reason": "Enough evidence.",
        },
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    behavioral = response.json()["behavioral_questions"]
    assert len(behavioral) == 2
    assert behavioral[0]["source"] == "career_conversation"
    assert behavioral[0]["question"] == "Describe a time you led a migration."
    assert behavioral[0]["context"] == "I led a 4-engineer migration off a legacy monolith."
    assert behavioral[1]["source"] == "suggested"


async def test_generate_works_without_a_career_conversation(api_client_factory) -> None:
    client, store, _gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    assert response.json()["behavioral_questions"] == []


async def test_generate_returns_409_for_a_completed_job_preparation(api_client_factory) -> None:
    client, store, _gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    resume_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    applied = await store.apply_resume_version(
        job_preparation.id,
        content=resume_version.content,
        selected_suggestion_ids=[],
        edited_texts={},
    )
    await store.save_job_preparation(
        applied.model_copy(update={"status": JobPreparationStatus.COMPLETED})
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 409


async def test_generate_sets_stage_initial_with_no_career_conversation_or_tailoring(
    api_client_factory,
) -> None:
    client, store, _gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.json()["stage"] == "initial"


async def test_first_generation_after_career_conversation_already_completed_lands_at_that_stage(
    api_client_factory,
) -> None:
    """A first-ever call has nothing to preserve, so it lands at the richest available stage."""
    client, store, _gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    await record_career_conversation(
        store,
        job_preparation.id,
        {
            "session_id": "s-1",
            "status": "complete",
            "history": [
                {
                    "topic": "Leadership",
                    "question": "Describe a time you led a migration.",
                    "answer": "I led a migration.",
                    "assistant_response": None,
                }
            ],
            "current_question": None,
            "stop_reason": "Enough evidence.",
        },
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.json()["stage"] == "career_conversation_enriched"


async def test_first_ever_generation_after_tailoring_already_applied_lands_at_that_stage(
    api_client_factory,
) -> None:
    client, store, gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    await record_generated_tailoring_plan(store, job_preparation.id, {"suggestions": []})
    await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="SUMMARY\nTailored backend engineer.",
        selected_suggestion_ids=[],
        edited_texts={},
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    assert response.json()["stage"] == "tailoring_aligned"
    # A single `generate()` call, already grounded in the applied resume
    # (see `resume_version_id` in the endpoint) -- no second, dedicated
    # tailoring-alignment call is needed for a first-ever generation.
    assert gateway.call_count == 1


def _seed_interview_preparation(
    *,
    stage: InterviewPreparationStage,
    behavioral_questions: list[BehavioralQuestion] | None = None,
) -> dict:
    result = InterviewPreparationResult(
        system_design_questions=[
            SystemDesignQuestion(
                question="Design a distributed document-analysis pipeline.",
                rationale="The resume shows large-scale backend systems experience.",
            )
        ],
        coding_questions=[
            CodingQuestion(
                title="Merge Intervals",
                topic="Sorting",
                difficulty=Difficulty.MEDIUM,
                relevance="The role involves scheduling logic.",
            )
        ],
        behavioral_questions=behavioral_questions
        if behavioral_questions is not None
        else [
            BehavioralQuestion(
                question="Tell me about a challenging project.",
                source=BehavioralQuestionSource.SUGGESTED,
                context=None,
            )
        ],
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        stage=stage,
    )
    return result.model_dump(mode="json")


async def test_career_conversation_enrichment_preserves_technical_questions_without_an_llm_call(
    api_client_factory,
) -> None:
    client, store, gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    seeded = _seed_interview_preparation(stage=InterviewPreparationStage.INITIAL)
    await record_interview_preparation(store, job_preparation.id, seeded)
    await record_career_conversation(
        store,
        job_preparation.id,
        {
            "session_id": "s-1",
            "status": "complete",
            "history": [
                {
                    "topic": "Leadership",
                    "question": "Describe a time you led a migration.",
                    "answer": "I led a 4-engineer migration off a legacy monolith.",
                    "assistant_response": None,
                }
            ],
            "current_question": None,
            "stop_reason": "Enough evidence.",
        },
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "career_conversation_enriched"
    assert body["system_design_questions"] == seeded["system_design_questions"]
    assert body["coding_questions"] == seeded["coding_questions"]
    behavioral = body["behavioral_questions"]
    assert len(behavioral) == 2
    assert behavioral[0]["source"] == "career_conversation"
    assert behavioral[0]["question"] == "Describe a time you led a migration."
    assert behavioral[1]["source"] == "suggested"
    assert behavioral[1]["question"] == "Tell me about a challenging project."
    # Stage 2 is purely deterministic -- the gateway is never called.
    assert gateway.call_count == 0


async def test_tailoring_enrichment_preserves_behavioral_questions_and_calls_the_gateway_once(
    api_client_factory,
) -> None:
    technical = GeneratedTechnicalPreparation(
        system_design_questions=[
            SystemDesignQuestion(
                question="Design a scalable resume-tailoring pipeline.",
                rationale="The tailored resume now emphasizes the tailoring engine.",
            )
        ],
        coding_questions=[
            CodingQuestion(
                title="Diff Two Strings",
                topic="Strings",
                difficulty=Difficulty.MEDIUM,
                relevance="The tailored resume emphasizes diff-based editing.",
            )
        ],
    )
    client, store, gateway = await api_client_factory(technical)
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )
    existing_behavioral = [
        BehavioralQuestion(
            question="Describe a time you led a migration.",
            source=BehavioralQuestionSource.CAREER_CONVERSATION,
            context="I led a 4-engineer migration off a legacy monolith.",
        )
    ]
    seeded = _seed_interview_preparation(
        stage=InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED,
        behavioral_questions=existing_behavioral,
    )
    await record_interview_preparation(store, job_preparation.id, seeded)
    await record_generated_tailoring_plan(store, job_preparation.id, {"suggestions": []})
    await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="SUMMARY\nTailored backend engineer.",
        selected_suggestion_ids=[],
        edited_texts={},
    )

    response = await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "tailoring_aligned"
    assert body["system_design_questions"][0]["question"] == (
        "Design a scalable resume-tailoring pipeline."
    )
    assert body["coding_questions"][0]["title"] == "Diff Two Strings"
    assert body["behavioral_questions"] == seeded["behavioral_questions"]
    assert gateway.call_count == 1


async def test_repeated_generation_never_creates_a_second_job_preparation(
    api_client_factory,
) -> None:
    client, store, _gateway = await api_client_factory(_generated())
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="JD",
        analysis_result=_ANALYSIS,
    )

    await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")
    await record_career_conversation(
        store,
        job_preparation.id,
        {
            "session_id": "s-1",
            "status": "complete",
            "history": [],
            "current_question": None,
            "stop_reason": "Enough evidence.",
        },
    )
    await client.post(f"/v1/job-preparations/{job_preparation.id}/interview-preparation")

    all_preparations = await store.list_job_preparations()
    assert len(all_preparations) == 1
    assert all_preparations[0].id == job_preparation.id
