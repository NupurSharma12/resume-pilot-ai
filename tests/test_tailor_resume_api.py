"""Integration tests for `POST /v1/tailor-resume`.

Builds its own app instance per test (matching
`test_career_conversation_api.py`'s pattern) so `get_tailoring_workflow`
can be overridden via FastAPI's dependency-override mechanism with a
workflow backed by the same kind of fake gateway used in
`test_tailoring_workflow.py`.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.api.v1.endpoints.tailor_resume import get_tailoring_workflow
from app.app import create_app
from app.core.config import Settings
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.tailored_resume import TailoredBullet, TailoredSection
from app.models.tailoring_plan import PlannedChange, TailoringAction, TailoringPlan
from app.prompts.resume_rewrite_prompt_builder import ResumeRewritePromptBuilder
from app.prompts.tailoring_planner_prompt_builder import TailoringPlannerPromptBuilder
from app.workflows.tailoring_workflow import TailoringWorkflow


class _FakeGateway:
    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        assert self._responses, "FakeGateway called more times than responses were programmed."
        return self._responses.pop(0)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover


_ANALYSIS_PAYLOAD = {
    "overall_assessment": {
        "overall_score": 70,
        "hiring_recommendation": {"decision": "Proceed", "reason": "Solid fit."},
        "summary": "Solid fit overall.",
    },
    "skill_matches": [],
    "matching_projects": [],
    "strengths": ["Strong backend ownership."],
    "weaknesses": ["Frontend experience is unclear."],
    "resume_improvements": [],
}

_CONVERSATION_PAYLOAD = {
    "session_id": "session-1",
    "status": "complete",
    "history": [
        {
            "topic": "Frontend",
            "question": "Have you built any UI applications?",
            "answer": "I built the internal dashboard using React and TypeScript.",
            "assistant_response": None,
        }
    ],
    "current_question": None,
    "stop_reason": "Enough evidence recovered.",
}

_REQUEST_PAYLOAD = {
    "resume": "Backend engineer with Python experience.",
    "job_description": "Looking for a full-stack engineer.",
    "resume_analysis": _ANALYSIS_PAYLOAD,
    "career_conversation": _CONVERSATION_PAYLOAD,
}


@pytest.fixture
async def api_client_factory():
    clients: list[AsyncClient] = []

    async def _factory(responses: list[BaseModel]) -> AsyncClient:
        settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
        app = create_app(settings)
        gateway = _FakeGateway(responses)
        app.dependency_overrides[get_tailoring_workflow] = lambda: TailoringWorkflow(
            evidence_store_builder=EvidenceStoreBuilder(),
            planner_prompt_builder=TailoringPlannerPromptBuilder(),
            rewrite_prompt_builder=ResumeRewritePromptBuilder(),
            gateway=gateway,
        )
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory

    for client in clients:
        await client.aclose()


async def test_tailor_resume_returns_plan_resume_and_validation_report(api_client_factory) -> None:
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing from the summary.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Built the internal dashboard using React and TypeScript.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    client = await api_client_factory([plan, section])

    response = await client.post("/v1/tailor-resume", json=_REQUEST_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["tailoring_plan"]["changes"][0]["section"] == "Summary"
    assert body["tailoring_plan"]["changes"][0]["action"] == "rewrite"
    assert body["validation_report"]["passed"] is True
    assert body["validation_report"]["accepted_count"] == 1
    assert body["tailored_resume"]["sections"][0]["heading"] == "Summary"
    assert (
        body["tailored_resume"]["sections"][0]["bullets"][0]["text"]
        == "Built the internal dashboard using React and TypeScript."
    )


async def test_tailor_resume_reports_rejected_bullets_without_failing_the_request(
    api_client_factory,
) -> None:
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Deployed the dashboard using Kubernetes.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    client = await api_client_factory([plan, section])

    response = await client.post("/v1/tailor-resume", json=_REQUEST_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["validation_report"]["passed"] is False
    assert body["validation_report"]["rejected_count"] == 1
    assert "Kubernetes" in body["validation_report"]["rejected_bullets"][0]["reason"]
    assert body["tailored_resume"]["sections"] == []


async def test_tailor_resume_with_invalid_plan_evidence_returns_500(api_client_factory) -> None:
    """An LLM that cites an evidence id that doesn't exist is a server-side failure, not a 4xx.

    Matches `analyze.py`/`career_conversation.py`'s established
    error-handling convention: gateway/workflow exceptions are logged and
    re-raised unchanged, falling through to FastAPI's default 500
    handling rather than being mapped to a specific status code.
    """
    bad_plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Some reason.",
                evidence_ids=["conversation-turn-99"],
            )
        ]
    )
    client = await api_client_factory([bad_plan])

    with pytest.raises(Exception, match="conversation-turn-99"):
        await client.post("/v1/tailor-resume", json=_REQUEST_PAYLOAD)


async def test_tailor_resume_works_with_empty_conversation_history(api_client_factory) -> None:
    payload = dict(_REQUEST_PAYLOAD)
    payload["career_conversation"] = {
        "session_id": "session-2",
        "status": "in_progress",
        "history": [],
        "current_question": None,
        "stop_reason": None,
    }
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.ADD_EMPHASIS,
                reason="Backend strength should be foregrounded.",
                evidence_ids=["analysis-strength-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Demonstrated strong backend ownership.",
                supporting_evidence_ids=["analysis-strength-1"],
            )
        ],
    )
    client = await api_client_factory([plan, section])

    response = await client.post("/v1/tailor-resume", json=payload)

    assert response.status_code == 200
    assert response.json()["validation_report"]["passed"] is True
