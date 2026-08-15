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
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow
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

    async def _factory(responses: list, reanalyze_responses: list | None = None) -> AsyncClient:
        settings = Settings(
            log_json=False, gemini_api_key="test-gemini-api-key", persistence_backend="memory"
        )
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
        # `/reanalyze` runs a second, independent `ResumeAnalysisWorkflow`
        # call (see `get_post_apply_analysis_workflow`) -- a separate
        # `FakeGateway` so its programmed responses never collide with
        # the suggestion-generation gateway's own queue.
        reanalyze_gateway = FakeGateway(reanalyze_responses or [])
        app.dependency_overrides[get_post_apply_analysis_workflow] = lambda: ResumeAnalysisWorkflow(
            prompt_builder=ResumeAnalysisPromptBuilder(),
            gateway=reanalyze_gateway,
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


async def test_generate_response_annotates_conflicting_suggestions(api_client_factory) -> None:
    """Two mutually exclusive rewrites of the same item are flagged before apply is ever tried."""
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

    response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())

    suggestions = response.json()["suggestions"]
    assert len(suggestions) == 2
    ids = {s["suggestion_id"] for s in suggestions}
    for suggestion in suggestions:
        other_id = next(iter(ids - {suggestion["suggestion_id"]}))
        assert suggestion["conflicts_with"] == [other_id]


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


def _reanalysis_result(score: int) -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=score,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=[
            SkillMatch(
                category="Backend", score=score, matched_skills=["Python"], missing_skills=[]
            ),
        ],
        matching_projects=[],
        strengths=["Strong backend ownership."],
        weaknesses=[],
        resume_improvements=[],
    )


async def _generate_and_apply(api_client_factory, *, reanalyze_responses: list | None = None):
    """Generate a plan, apply its one suggestion, and return `(client, plan_id)`.

    Shared setup for every `/reanalyze` test below -- `/reanalyze` only
    makes sense against a plan that's already been generated (and
    typically applied), same precondition the product flow enforces.
    """
    edits, text = _append_edit_and_text()
    client = await api_client_factory([edits, text], reanalyze_responses=reanalyze_responses)
    generate_response = await client.post("/v1/tailoring-suggestions", json=_generate_payload())
    plan_id = generate_response.json()["plan_id"]
    suggestion_id = generate_response.json()["suggestions"][0]["suggestion_id"]

    await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/apply",
        json={"selected_suggestion_ids": [suggestion_id], "edited_texts": {}},
    )
    return client, plan_id, suggestion_id


async def test_reanalyze_returns_improved_when_score_increases(api_client_factory) -> None:
    client, plan_id, suggestion_id = await _generate_and_apply(
        api_client_factory, reanalyze_responses=[_reanalysis_result(81)]
    )

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
        json={
            "previous_analysis": _ANALYSIS_PAYLOAD,
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    before_score = _ANALYSIS_PAYLOAD["overall_assessment"]["overall_score"]
    assert body["comparison"]["score_before"] == before_score
    assert body["comparison"]["score_after"] == 81
    assert body["comparison"]["score_delta"] == 11
    assert body["comparison"]["status"] == "improved"
    assert body["after_analysis"]["overall_assessment"]["overall_score"] == 81


async def test_reanalyze_returns_unchanged_when_score_is_equal(api_client_factory) -> None:
    before_score = _ANALYSIS_PAYLOAD["overall_assessment"]["overall_score"]
    client, plan_id, suggestion_id = await _generate_and_apply(
        api_client_factory, reanalyze_responses=[_reanalysis_result(before_score)]
    )

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
        json={
            "previous_analysis": _ANALYSIS_PAYLOAD,
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
        },
    )

    assert response.status_code == 200
    comparison = response.json()["comparison"]
    assert comparison["score_delta"] == 0
    assert comparison["status"] == "unchanged"


async def test_reanalyze_returns_decreased_when_score_drops(api_client_factory) -> None:
    client, plan_id, suggestion_id = await _generate_and_apply(
        api_client_factory, reanalyze_responses=[_reanalysis_result(60)]
    )

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
        json={
            "previous_analysis": _ANALYSIS_PAYLOAD,
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
        },
    )

    assert response.status_code == 200
    comparison = response.json()["comparison"]
    before_score = _ANALYSIS_PAYLOAD["overall_assessment"]["overall_score"]
    assert comparison["score_delta"] == 60 - before_score
    assert comparison["status"] == "decreased"


async def test_reanalyze_failure_does_not_fabricate_a_comparison(api_client_factory) -> None:
    """No programmed reanalyze response -- the FakeGateway raises, simulating a real failure.

    The endpoint must not swallow this into a fake "unchanged"/degraded
    comparison -- the underlying failure propagates unchanged (exactly
    like `/analyze` does on its own failure path -- see
    `reanalyze_after_apply`'s docstring), never a 200 with an invented
    score. No comparison/analysis is returned at all.
    """
    client, plan_id, suggestion_id = await _generate_and_apply(
        api_client_factory, reanalyze_responses=[]
    )

    with pytest.raises(AssertionError, match="FakeGateway called more times"):
        await client.post(
            f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
            json={
                "previous_analysis": _ANALYSIS_PAYLOAD,
                "selected_suggestion_ids": [suggestion_id],
                "edited_texts": {},
            },
        )


async def test_reanalyze_unknown_plan_id_returns_404(api_client_factory) -> None:
    client = await api_client_factory([])

    response = await client.post(
        "/v1/tailoring-suggestions/does-not-exist/reanalyze",
        json={
            "previous_analysis": _ANALYSIS_PAYLOAD,
            "selected_suggestion_ids": [],
            "edited_texts": {},
        },
    )

    assert response.status_code == 404


async def test_reanalyze_rejects_a_client_supplied_job_description(api_client_factory) -> None:
    """The request schema has no job_description field at all -- extra="forbid" rejects one.

    This is the enforcement mechanism behind this endpoint's core
    invariant: the job description always comes from `StoredPlan`
    (the one this plan was actually generated against), never from the
    client, so a "before" and "after" comparison can never silently
    drift onto different job descriptions.
    """
    client, plan_id, suggestion_id = await _generate_and_apply(api_client_factory)

    response = await client.post(
        f"/v1/tailoring-suggestions/{plan_id}/reanalyze",
        json={
            "previous_analysis": _ANALYSIS_PAYLOAD,
            "selected_suggestion_ids": [suggestion_id],
            "edited_texts": {},
            "job_description": "A different job entirely.",
        },
    )

    assert response.status_code == 422
