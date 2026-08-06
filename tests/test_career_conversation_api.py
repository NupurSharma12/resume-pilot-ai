"""Integration tests for the Career Conversation HTTP endpoints.

Builds its own app instance per test (rather than the shared `client`
fixture) so `get_career_conversation_workflow` can be overridden via
FastAPI's dependency-override mechanism with a workflow backed by the same
`FakeGateway` used in `test_career_conversation_workflow.py` — see that
module's docstring for why the generic `MockGateway` can't exercise this
endpoint's happy path.
"""

import asyncio

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

    async def _factory(
        decisions: list[ConversationTurnDecision], delay_seconds: float = 0
    ) -> AsyncClient:
        settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
        app = create_app(settings)
        gateway = FakeGateway(decisions, delay_seconds=delay_seconds)
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


async def test_assistant_response_surfaces_in_the_response_body(api_client_factory) -> None:
    client = await api_client_factory(
        [
            _continue_decision(confidence=30),
            _continue_decision(
                confidence=50,
                assistant_response="Sure — I mean the whole platform, not just your team's part.",
            ),
            _stop_decision(confidence=95, reason="No gaps remain."),
        ]
    )
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    assert start_response.json()["current_question"]["assistant_response"] is None
    session_id = start_response.json()["session_id"]

    response = await client.post(
        f"/v1/career-conversation/{session_id}/answer",
        json={"answer": "Wait, do you mean the whole platform or just my team's part?"},
    )

    body = response.json()
    assert (
        body["current_question"]["assistant_response"]
        == "Sure — I mean the whole platform, not just your team's part."
    )

    # Once that question is answered too, the assistant_response should
    # travel with it into history.
    second = await client.post(
        f"/v1/career-conversation/{session_id}/answer",
        json={"answer": "Got it, the whole platform."},
    )
    second_body = second.json()
    assert (
        second_body["history"][-1]["assistant_response"]
        == "Sure — I mean the whole platform, not just your team's part."
    )


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


async def test_concurrent_answers_for_same_question_return_409_not_500(api_client_factory) -> None:
    """Regression test for a real, reproduced race condition.

    Two requests answering the *same currently-open* question
    concurrently (e.g. a client retry racing an original request still
    being processed) must not crash. Both pass the endpoint's fast-path
    "not already complete" check before either finishes — the in-lock
    recheck (see `submit_career_conversation_answer`'s docstring) is what
    turns the loser into a clean `409` instead of an unhandled `500` from
    `ConversationSession.record_answer` finding `current_question` already
    cleared by the winner. `delay_seconds` on the fake gateway is what
    reliably reproduces the interleaving — see `FakeGateway`'s docstring.
    """
    client = await api_client_factory(
        [
            _continue_decision(confidence=30),
            _stop_decision(confidence=95, reason="No gaps remain."),
        ],
        delay_seconds=0.05,
    )
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]
    assert start_response.json()["status"] == "in_progress"

    answer_payload = {"answer": "I used React for the internal dashboard."}

    async def submit():
        return await client.post(
            f"/v1/career-conversation/{session_id}/answer", json=answer_payload
        )

    results = await asyncio.gather(submit(), submit())

    statuses = sorted(result.status_code for result in results)
    assert statuses == [200, 409]

    # And the session itself is left in a consistent, valid end state --
    # not corrupted by the race.
    final = await client.get(f"/v1/career-conversation/{session_id}")
    body = final.json()
    assert body["status"] == "complete"
    assert len(body["history"]) == 1


async def test_internal_turn_failure_leaves_session_recoverable_not_corrupted(
    api_client_factory,
) -> None:
    """Regression test for the session-corruption bug fixed in `CareerConversationWorkflow`.

    A failure while generating the *next* turn (standing in here for a
    schema-invalid LLM response, an inconsistent should_stop/question
    decision, or every provider in the chain failing) must not silently
    consume the candidate's answer with no replacement question. Asserts
    the full recoverable story end to end, through the real HTTP layer:
    the failing request surfaces as a 500 (this app's established
    convention for an unclassified internal failure -- see
    `analyze.py`/`tailor_resume.py`), a `GET` immediately afterward shows
    the session exactly as it was *before* the failed request (same open
    question, same empty history, still `in_progress`), and resubmitting
    the same answer afterward succeeds normally with no duplication.
    """
    client = await api_client_factory(
        [
            _continue_decision(confidence=30),
            RuntimeError("all providers failed"),
            _continue_decision(confidence=50),
        ]
    )
    start_response = await client.post("/v1/career-conversation", json=_START_PAYLOAD)
    session_id = start_response.json()["session_id"]
    question_before = start_response.json()["current_question"]

    with pytest.raises(RuntimeError, match="all providers failed"):
        await client.post(
            f"/v1/career-conversation/{session_id}/answer",
            json={"answer": "I used React for the internal dashboard."},
        )

    # The session survived the failure completely intact.
    after_failure = await client.get(f"/v1/career-conversation/{session_id}")
    assert after_failure.status_code == 200
    after_failure_body = after_failure.json()
    assert after_failure_body["status"] == "in_progress"
    assert after_failure_body["history"] == []
    assert after_failure_body["current_question"] == question_before

    # A client's own retry -- resubmitting the same answer against the
    # still-open question -- now succeeds normally, exactly as if the
    # failed attempt had never happened. Same `client`/session: its
    # gateway's third queued decision is what this retry consumes.
    retry_response = await client.post(
        f"/v1/career-conversation/{session_id}/answer",
        json={"answer": "I used React for the internal dashboard."},
    )
    assert retry_response.status_code == 200
    retry_body = retry_response.json()
    assert len(retry_body["history"]) == 1
    assert retry_body["history"][0]["answer"] == "I used React for the internal dashboard."
    assert retry_body["status"] == "in_progress"
    assert retry_body["current_question"] is not None
