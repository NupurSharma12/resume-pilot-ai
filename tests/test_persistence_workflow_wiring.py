"""End-to-end proof that `job_preparation_id` threads through the real API surface.

`tests/test_job_preparation_persistence.py` proves each durable-write
boundary works in isolation, against the orchestration functions directly.
This file proves the *wiring*: that a `job_preparation_id` returned by a
real `POST /v1/analyze` call, carried by the client through
`/career-conversation`'s `job_preparation_id` and `/tailoring-suggestions`'
`job_preparation_id`, actually reaches every later durable write with no
further client action beyond echoing that one id -- `/answer`, `/apply`,
and `/reanalyze` never need it re-sent (see `StoredPlan.job_preparation_id`/
`ConversationSession.job_preparation_id`).

One app instance, several dependency-overridden `FakeGateway`s -- mirrors
`test_career_conversation_api.py`/`test_tailoring_suggestions_api.py`'s
own pattern, combined into a single request sequence instead of testing
each endpoint in isolation. `app.state.persistence_store` is left
un-overridden (the real `InMemoryPersistenceStore` `create_app` builds
under `PERSISTENCE_BACKEND=memory`), since the wiring under test here is
whether the real dependency reaches the real store, not a stand-in.
"""

from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.analyze import get_resume_analysis_workflow
from app.api.v1.endpoints.career_conversation import get_career_conversation_workflow
from app.api.v1.endpoints.tailoring_suggestions import (
    get_post_apply_analysis_workflow,
    get_tailoring_suggestion_workflow,
)
from app.app import create_app
from app.core.config import Settings
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
    SkillMatch,
)
from app.models.tailoring_suggestions import (
    PlannedEdits,
    SuggestedEdit,
    SuggestionOperation,
    SuggestionText,
)
from app.persistence.models import JobPreparationStatus, ResumeVersionSource
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.workflows.career_conversation_workflow import CareerConversationWorkflow
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow
from app.workflows.tailoring_suggestion_workflow import TailoringSuggestionWorkflow
from tests.test_career_conversation_workflow import FakeGateway as ConversationFakeGateway
from tests.test_career_conversation_workflow import _stop_decision
from tests.test_tailoring_suggestion_workflow import FakeGateway as TailoringFakeGateway

_RESUME_TEXT = (
    "SUMMARY\n"
    "Backend engineer with strong Python skills.\n\n"
    "SKILLS\n"
    "- Python\n\n"
    "EXPERIENCE\n"
    "- Built internal tools using Python.\n"
)


def _result(score: int) -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=score,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=[
            SkillMatch(
                category="Backend", score=score, matched_skills=["Python"], missing_skills=[]
            )
        ],
        matching_projects=[],
        strengths=["Strong backend ownership."],
        weaknesses=[],
        resume_improvements=[],
    )


def _skills_item_id() -> str:
    structured = ResumeStructureParser().parse(_RESUME_TEXT)
    return next(
        item.item_id
        for section in structured.sections
        for item in section.items
        if item.text == "Python"
    )


async def test_job_preparation_id_threads_through_the_full_workflow() -> None:
    settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
    app = create_app(settings)
    app.dependency_overrides[get_resume_analysis_workflow] = lambda: ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=_AnalyzeFakeGateway(_result(70)),
    )
    app.dependency_overrides[get_career_conversation_workflow] = lambda: CareerConversationWorkflow(
        CareerConversationPromptBuilder(),
        ConversationFakeGateway([_stop_decision(confidence=95, reason="Enough evidence.")]),
    )
    item_id = _skills_item_id()
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="TypeScript experience is missing.",
                evidence_ids=[f"resume-{item_id}"],
            )
        ]
    )
    text = SuggestionText(
        suggested_text="Python, TypeScript", evidence_ids=[f"resume-{item_id}"], confidence=90
    )
    app.dependency_overrides[get_tailoring_suggestion_workflow] = lambda: (
        TailoringSuggestionWorkflow(
            structure_parser=ResumeStructureParser(),
            evidence_store_builder=EvidenceStoreBuilder(),
            planner_prompt_builder=SuggestionPlannerPromptBuilder(),
            rewrite_prompt_builder=SuggestionRewritePromptBuilder(),
            gateway=TailoringFakeGateway([edits, text]),
        )
    )
    app.dependency_overrides[get_post_apply_analysis_workflow] = lambda: ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=_AnalyzeFakeGateway(_result(85)),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Analyze -- boundaries A + B + C.
        analyze_response = await client.post(
            "/v1/analyze", json={"resume": _RESUME_TEXT, "job_description": "Backend role."}
        )
        assert analyze_response.status_code == 200
        analyze_body = analyze_response.json()
        job_preparation_id = analyze_body["job_preparation_id"]
        assert job_preparation_id is not None

        # 2. Career Conversation -- boundary D. Completes on the first
        # turn (a stop decision), which start_career_conversation itself
        # must persist -- there is no separate /answer call at all here.
        conversation_response = await client.post(
            "/v1/career-conversation",
            json={
                "resume": _RESUME_TEXT,
                "job_description": "Backend role.",
                "resume_analysis": analyze_body,
                "job_preparation_id": job_preparation_id,
            },
        )
        assert conversation_response.status_code == 200
        assert conversation_response.json()["status"] == "complete"

        # 3. Generate tailoring suggestions -- boundary E (first half).
        generate_response = await client.post(
            "/v1/tailoring-suggestions",
            json={
                "resume": _RESUME_TEXT,
                "job_description": "Backend role.",
                "resume_analysis": analyze_body,
                "career_conversation": conversation_response.json(),
                "job_preparation_id": job_preparation_id,
            },
        )
        assert generate_response.status_code == 200
        generate_body = generate_response.json()
        plan_id = generate_body["plan_id"]
        suggestion_id = generate_body["suggestions"][0]["suggestion_id"]

        # 4. Apply -- boundaries E (second half) + F. No job_preparation_id
        # in this request body at all -- it's carried on the stored plan.
        apply_response = await client.post(
            f"/v1/tailoring-suggestions/{plan_id}/apply",
            json={"selected_suggestion_ids": [suggestion_id], "edited_texts": {}},
        )
        assert apply_response.status_code == 200

        # 5. Reanalyze -- boundary G. Also no job_preparation_id here.
        reanalyze_response = await client.post(
            f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
            json={
                "previous_analysis": analyze_body,
                "selected_suggestion_ids": [suggestion_id],
                "edited_texts": {},
            },
        )
        assert reanalyze_response.status_code == 200

    store = app.state.persistence_store
    job_preparation = await store.get_job_preparation(UUID(job_preparation_id))
    assert job_preparation is not None
    assert job_preparation.status == JobPreparationStatus.ACTIVE

    assert job_preparation.analysis_result["overall_assessment"]["overall_score"] == 70
    assert job_preparation.career_conversation["status"] == "complete"
    assert job_preparation.tailoring_plan["generated_plan"]["plan_id"] == plan_id
    assert job_preparation.tailoring_plan["selection"]["selected_suggestion_ids"] == [suggestion_id]
    assert job_preparation.post_apply_analysis["comparison"]["score_before"] == 70
    assert job_preparation.post_apply_analysis["comparison"]["score_after"] == 85

    assert job_preparation.applied_resume_version_id is not None
    applied_version = await store.get_resume_version(job_preparation.applied_resume_version_id)
    assert applied_version.source == ResumeVersionSource.APPLIED
    assert "Python, TypeScript" in applied_version.content

    source_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    assert source_version.version_number == 1
    assert applied_version.resume_id == source_version.resume_id


class _AnalyzeFakeGateway:
    """Minimal `LLMGateway`: always returns a fixed, caller-chosen `ResumeAnalysisResult`."""

    provider_name = "fake"
    supports_structured_output = True

    def __init__(self, result: ResumeAnalysisResult) -> None:
        self._result = result

    async def generate_structured(self, request, response_model):
        return self._result

    async def generate(self, request):
        raise NotImplementedError

    async def stream(self, request):
        raise NotImplementedError
        yield  # pragma: no cover
