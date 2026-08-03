"""Integration tests for the Career Conversation HTTP endpoints.

Builds its own app instance per test (rather than the shared `client`
fixture) so `get_career_conversation_workflow` can be overridden via
FastAPI's dependency-override mechanism with a workflow backed by the same
`FakeGateway` used in `test_career_conversation_workflow.py` — see that
module's docstring for why the generic `MockGateway` can't exercise this
endpoint's happy path.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.career_conversation import get_career_conversation_workflow
from app.app import create_app
from app.core.config import Settings
from app.models.career_conversation import ConversationTurnDecision, EstimatedImpact
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.workflows.career_conversation_workflow import CareerConversationWorkflow
from tests.test_career_conversation_workflow import FakeGateway, _continue_decision, _stop_decision

_ANALYSIS_PAYLOAD = {
    "overall_assessment": {
        "overall_score": 70,
        "hiring_recommendation": {"decision": "Proceed", "reason": "Solid fit."},
        "summary": "Solid fit overall.",
    },
    "skill_matches": [
        {
            "category": "Frontend",
            "score": 50,
            "matched_skills": ["JavaScript"],
            "missing_skills": ["React"],
        }
    ],
    "matching_projects": [],
    "strengths": ["Strong backend experience."],
    "weaknesses": ["Frontend framework experience is unclear."],
    "resume_improvements": [],
}

_START_PAYLOAD = {
    "resume": "Built internal tooling for the platform team.",
    "job_description": "Looking for a frontend engineer with React experience.",
    "resume_analysis": _ANALYSIS_PAYLOAD,
}


@pytest.fixture
async def api_client_factory():
    """Return a factory building a fresh `(client, fake_gateway)` per test.

    Each call constructs its own app instance and overrides
    `get_career_conversation_workflow` to return a workflow backed by a
    `FakeGateway` seeded with `decisions` — so each test controls exactly
    what the "LLM" says on each turn.
    """
    clients: list[AsyncClient] = []

    async def _factory(decisions: list[ConversationTurnDecision]) -> AsyncClient:
        settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
        app = create_app(settings)
        gateway = FakeGateway(decisions)
        app.dependency_overrides[get_career_conversation_workflow] = lambda: (
            CareerConversationWorkflow(CareerConversationPromptBuilder(), gateway)
        )
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory

    for client in clients:
        await client.aclose()


async def test_start_returns_first_question(api_client_factory) -> None:
    client = await api_client_factory([_continue_decision(confidence=30)])

    response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["history"] == []
    assert body["current_question"]["topic"] == "Frontend framework experience"
    assert body["current_question"]["estimated_impact"] == EstimatedImpact.HIGH.value
    assert body["stop_reason"] is None


async def test_get_returns_state_without_calling_the_gateway_again(api_client_factory) -> None:
    client = await api_client_factory([_continue_decision(confidence=30)])
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]

    response = await client.get(f"/v1/career-conversation/{session_id}")

    assert response.status_code == 200
    assert response.json() == start_response.json()


async def test_answer_advances_the_conversation(api_client_factory) -> None:
    client = await api_client_factory(
        [_continue_decision(confidence=30), _continue_decision(confidence=50)]
    )
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]

    response = await client.post(
        f"/v1/career-conversation/{session_id}/answer",
        json={"answer": "I used React for the internal dashboard."},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["history"]) == 1
    assert body["history"][0]["answer"] == "I used React for the internal dashboard."
    assert body["status"] == "in_progress"
    assert body["current_question"] is not None


async def test_answer_completes_when_llm_signals_stop(api_client_factory) -> None:
    client = await api_client_factory(
        [
            _continue_decision(confidence=30),
            _stop_decision(confidence=92, reason="Enough evidence."),
        ]
    )
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]

    response = await client.post(
        f"/v1/career-conversation/{session_id}/answer",
        json={"answer": "I used React for the internal dashboard."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["current_question"] is None
    assert body["stop_reason"] == "Enough evidence."


async def test_get_unknown_session_returns_404(api_client_factory) -> None:
    client = await api_client_factory([])

    response = await client.get("/v1/career-conversation/does-not-exist")

    assert response.status_code == 404


async def test_answer_unknown_session_returns_404(api_client_factory) -> None:
    client = await api_client_factory([])

    response = await client.post(
        "/v1/career-conversation/does-not-exist/answer", json={"answer": "Anything."}
    )

    assert response.status_code == 404


async def test_answer_after_completion_returns_409(api_client_factory) -> None:
    client = await api_client_factory([_stop_decision(confidence=95, reason="No gaps remain.")])
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]
    assert start_response.json()["status"] == "complete"

    response = await client.post(
        f"/v1/career-conversation/{session_id}/answer", json={"answer": "Too late."}
    )

    assert response.status_code == 409
