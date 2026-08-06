"""Integration tests for the Interactive Tailoring HTTP endpoints.

Builds its own app instance per test (rather than the shared `client`
fixture) so `get_tailoring_suggestion_workflow` can be overridden via
FastAPI's dependency-override mechanism with a workflow backed by the
same `FakeGateway` used in `test_tailoring_suggestion_workflow.py` — see
that module's docstring for why. Also covers a real cross-origin-header
regression found during manual HTTP smoke testing: without
`expose_headers` on the CORS middleware, a browser `fetch()` from the
frontend's dev origin could not read `Content-Disposition`/
`X-Export-Fidelity` even though curl saw them fine (see `app.app`'s
`create_app`).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.tailoring_suggestions import get_tailoring_suggestion_workflow
from app.app import create_app
from app.core.config import Settings
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.models.tailoring_suggestions import (
    PlannedEdits,
    SuggestedEdit,
    SuggestionOperation,
    SuggestionText,
)
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.workflows.tailoring_suggestion_workflow import TailoringSuggestionWorkflow
from tests.test_tailoring_suggestion_workflow import FakeGateway

_RESUME_TEXT = (
    "SUMMARY\n"
    "Backend engineer with strong Python skills.\n\n"
    "SKILLS\n"
    "- Python\n"
    "- Django\n\n"
    "EXPERIENCE\n"
    "- Built internal tools using Python and Django.\n"
)

_ANALYSIS_PAYLOAD = {
    "overall_assessment": {
        "overall_score": 70,
        "hiring_recommendation": {"decision": "Proceed", "reason": "Solid fit."},
        "summary": "Solid fit overall.",
    },
    "skill_matches": [
        {"category": "Backend", "score": 80, "matched_skills": ["Python"], "missing_skills": []},
    ],
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
    "stop_reason": "Enough evidence.",
}


def _skills_item_id() -> str:
    structured = ResumeStructureParser().parse(_RESUME_TEXT)
    return next(
        item.item_id
        for section in structured.sections
        for item in section.items
        if item.text == "Python"
    )


@pytest.fixture
async def api_client_factory():
    """Return a factory building a fresh `(client)` backed by a `FakeGateway` per test."""
    clients: list[AsyncClient] = []

    async def _factory(responses: list) -> AsyncClient:
        settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
        app = create_app(settings)
        gateway = FakeGateway(responses)
        app.dependency_overrides[get_tailoring_suggestion_workflow] = lambda: (
            TailoringSuggestionWorkflow(
                structure_parser=ResumeStructureParser(),
                evidence_store_builder=EvidenceStoreBuilder(),
                planner_prompt_builder=SuggestionPlannerPromptBuilder(),
                rewrite_prompt_builder=SuggestionRewritePromptBuilder(),
                gateway=gateway,
            )
        )
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client

    yield _factory

    for client in clients:
        await client.aclose()


def _generate_payload(custom_instructions: str | None = None) -> dict:
    return {
        "resume": _RESUME_TEXT,
        "job_description": "Looking for a full-stack engineer.",
        "resume_analysis": _ANALYSIS_PAYLOAD,
        "career_conversation": _CONVERSATION_PAYLOAD,
        "custom_instructions": custom_instructions,
        "resume_filename": "resume.txt",
    }


def _append_edit_and_text() -> tuple[PlannedEdits, SuggestionText]:
    item_id = _skills_item_id()
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="TypeScript experience is missing.",
                evidence_ids=[f"resume-{item_id}", "conversation-turn-1"],
            )
        ]
    )
    text = SuggestionText(
        suggested_text="Python, TypeScript",
        evidence_ids=[f"resume-{item_id}", "conversation-turn-1"],
        confidence=90,
    )
    return edits, text


async def test_generate_returns_stable_plan_id_and_suggestions(api_client_factory) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])

    response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"]
    assert len(body["suggestions"]) == 1
    suggestion = body["suggestions"][0]
    assert suggestion["suggestion_id"] == "suggestion-0"
    assert suggestion["operation"] == "append"
    assert suggestion["target_section_id"]
    assert suggestion["target_item_id"]
    assert suggestion["current_text"] == "Python"
    assert suggestion["suggested_text"] == "Python, TypeScript"
    assert suggestion["reason"]
    assert suggestion["evidence_ids"]
    assert suggestion["validation_status"] == "supported_by_both"
    # Default export format for a .txt upload should be txt.
    assert body["default_export_format"] == "txt"
    assert set(body["available_export_formats"]) == {"txt", "markdown", "docx", "pdf"}


async def test_apply_only_applies_selected_suggestions(api_client_factory) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={"selected_suggestion_ids": [], "edited_texts": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_suggestion_ids"] == []
    assert "Python" in body["final_resume_text"]
    assert "TypeScript" not in body["final_resume_text"]
    assert body["final_validation"]["is_valid"] is True


async def test_apply_with_selected_suggestion_updates_final_resume(api_client_factory) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]
    suggestion_id = generate_response.json()["suggestions"][0]["suggestion_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={"selected_suggestion_ids": [suggestion_id], "edited_texts": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied_suggestion_ids"] == [suggestion_id]
    assert "Python, TypeScript" in body["final_resume_text"]


async def test_apply_unknown_suggestion_id_returns_400(api_client_factory) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={"selected_suggestion_ids": ["does-not-exist"], "edited_texts": {}},
    )

    assert response.status_code == 400
    assert "does-not-exist" in response.json()["detail"]


async def test_apply_unknown_plan_id_returns_404(api_client_factory) -> None:
    client = await api_client_factory([])

    response = await client.post(
        "/v1/tailoring-suggestions/does-not-exist/apply",
        json={"selected_suggestion_ids": [], "edited_texts": {}},
    )

    assert response.status_code == 404


async def test_apply_conflicting_suggestions_returns_409(api_client_factory) -> None:
    item_id = _skills_item_id()
    edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="Add TypeScript.",
                evidence_ids=["conversation-turn-1"],
            ),
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.UPDATE,
                reason="Reword the skills line.",
                evidence_ids=["conversation-turn-1"],
            ),
        ]
    )
    client = await api_client_factory(
        [
            edits,
            SuggestionText(
                suggested_text="Python, TypeScript",
                evidence_ids=["conversation-turn-1"],
                confidence=80,
            ),
            SuggestionText(
                suggested_text="Python and TypeScript expert",
                evidence_ids=["conversation-turn-1"],
                confidence=80,
            ),
        ]
    )
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    suggestion_ids = [s["suggestion_id"] for s in generate_response.json()["suggestions"]]
    plan_id = generate_response.json()["plan_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={"selected_suggestion_ids": suggestion_ids, "edited_texts": {}},
    )

    assert response.status_code == 409


async def test_apply_edited_text_with_unsupported_claim_returns_422(api_client_factory) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]
    suggestion_id = generate_response.json()["suggestions"][0]["suggestion_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {suggestion_id: "Python, TypeScript, Kubernetes"},
        },
    )

    assert response.status_code == 422
    assert "Kubernetes" in response.json()["detail"]


@pytest.mark.parametrize(
    ("export_format", "content_type", "expected_fidelity"),
    [
        ("txt", "text/plain", "approximate_style"),
        ("markdown", "text/markdown", "approximate_style"),
        (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "regenerated_template",
        ),
        ("pdf", "application/pdf", "regenerated_template"),
    ],
)
async def test_export_returns_correct_headers_and_content_type(
    api_client_factory, export_format, content_type, expected_fidelity
) -> None:
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]
    suggestion_id = generate_response.json()["suggestions"][0]["suggestion_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/export",
        json={
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
            "format": export_format,
            "filename_base": "../../etc/passwd; rm -rf",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["x-export-fidelity"] == expected_fidelity
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "/" not in disposition
    assert ".." not in disposition
    assert len(response.content) > 0


async def test_export_headers_are_exposed_for_cross_origin_requests(api_client_factory) -> None:
    """Regression test: browsers only expose safelisted response headers to JS by default.

    Without `expose_headers=["Content-Disposition", "X-Export-Fidelity"]`
    on the CORS middleware (see `app.app.create_app`), a frontend
    `fetch()` from a different origin would get `null` back from
    `response.headers.get("Content-Disposition")` even though the raw
    HTTP response carries it fine -- this was caught during manual HTTP
    smoke testing, not by any prior unit test.
    """
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text])
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]
    suggestion_id = generate_response.json()["suggestions"][0]["suggestion_id"]

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/export",
        json={
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
            "format": "txt",
            "filename_base": None,
        },
        headers={"Origin": "http://localhost:5173"},
    )

    exposed = response.headers["access-control-expose-headers"]
    assert "Content-Disposition" in exposed
    assert "X-Export-Fidelity" in exposed


async def test_export_unknown_plan_id_returns_404(api_client_factory) -> None:
    client = await api_client_factory([])

    response = await client.post(
        "/v1/tailoring-suggestions/does-not-exist/export",
        json={"selected_suggestion_ids": [], "edited_texts": {}, "format": "txt"},
    )

    assert response.status_code == 404


async def test_custom_instructions_do_not_authorize_unsupported_facts(api_client_factory) -> None:
    """A custom instruction alone is never enough evidence for a suggestion.

    Simulates a `FakeGateway` "misbehaving" by proposing an edit
    grounded in nothing but the instruction text -- since the edit still
    cites zero evidence_ids, the workflow's own contract check rejects
    it before any rewrite call, regardless of what the instruction said.
    """
    item_id = _skills_item_id()
    bad_edits = PlannedEdits(
        edits=[
            SuggestedEdit(
                target_section_id="section-1",
                target_item_id=item_id,
                operation=SuggestionOperation.APPEND,
                reason="The candidate asked for this.",
                evidence_ids=[],
            )
        ]
    )
    client = await api_client_factory([bad_edits])

    response = await client.post(
        "/v1/tailoring-suggestions",
        json=_generate_payload(custom_instructions="Add 5 years of Kubernetes experience."),
    )

    assert response.status_code == 502
