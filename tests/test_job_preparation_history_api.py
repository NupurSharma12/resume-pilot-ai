"""Integration tests for the History endpoints (`GET /v1/job-preparations*`).

Builds its own app instance (rather than the shared `client` fixture) so
each test gets a fresh, isolated `InMemoryPersistenceStore` to seed
directly via `app.orchestration.job_preparation_persistence` -- the same
pattern `test_analyze_api.py`/`test_persistence_workflow_wiring.py`
already use. Deterministic: no LLM gateway is exercised at all, since
these endpoints only ever read already-persisted state.
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.app import create_app
from app.core.config import Settings
from app.orchestration.job_preparation_persistence import (
    record_applied_tailoring_selection,
    record_career_conversation,
    record_generated_tailoring_plan,
    record_post_apply_analysis,
    start_job_preparation,
)

_ANALYSIS = {"overall_assessment": {"overall_score": 70}, "strengths": ["Strong backend."]}


@pytest.fixture
async def api_client_factory():
    """Return a factory building a fresh `(client, persistence_store)` per test."""
    clients: list[AsyncClient] = []

    async def _factory() -> tuple[AsyncClient, object]:
        settings = Settings(log_json=False, gemini_api_key="test-gemini-api-key")
        app = create_app(settings)
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return client, app.state.persistence_store

    yield _factory

    for client in clients:
        await client.aclose()


async def test_list_returns_empty_when_nothing_exists(api_client_factory) -> None:
    client, _store = await api_client_factory()

    response = await client.get("/v1/job-preparations")

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_list_returns_a_lightweight_summary_without_jsonb_payloads(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer\nBuild things.",
        analysis_result=_ANALYSIS,
        company="Acme Corp",
    )

    response = await client.get("/v1/job-preparations")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == str(job_preparation.id)
    assert item["job_title"] == "Senior Backend Engineer"
    assert item["company"] == "Acme Corp"
    assert item["resume_name"]
    assert "created_at" in item
    assert "updated_at" in item
    assert set(item["checkpoints"]) == {
        "initial_analysis_completed_at",
        "career_conversation_completed_at",
        "tailoring_plan_completed_at",
        "applied_at",
        "post_apply_analysis_completed_at",
    }
    # Deliberately lightweight -- no JSONB payload fields at all.
    assert "analysis_result" not in item
    assert "career_conversation" not in item
    assert "tailoring_plan" not in item
    assert "post_apply_analysis" not in item
    assert "job_description" not in item


async def test_list_reflects_only_completed_checkpoints(api_client_factory) -> None:
    client, store = await api_client_factory()
    await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    response = await client.get("/v1/job-preparations")

    checkpoints = response.json()["items"][0]["checkpoints"]
    assert checkpoints["initial_analysis_completed_at"] is not None
    assert checkpoints["career_conversation_completed_at"] is None
    assert checkpoints["tailoring_plan_completed_at"] is None
    assert checkpoints["applied_at"] is None
    assert checkpoints["post_apply_analysis_completed_at"] is None


async def test_list_orders_by_updated_at_descending(api_client_factory) -> None:
    client, store = await api_client_factory()
    first = await start_job_preparation(
        store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
    )
    second = await start_job_preparation(
        store, resume_text="Resume B", job_description="JD B", analysis_result=_ANALYSIS
    )
    # Touch `first` again so it becomes the most recently updated.
    await record_career_conversation(store, first.id, {"session_id": "s-1", "status": "complete"})

    response = await client.get("/v1/job-preparations")

    ids_in_order = [item["id"] for item in response.json()["items"]]
    assert ids_in_order == [str(first.id), str(second.id)]


async def test_list_supports_company_and_job_title_filters(api_client_factory) -> None:
    client, store = await api_client_factory()
    matching = await start_job_preparation(
        store,
        resume_text="Resume A",
        job_description="JD A",
        analysis_result=_ANALYSIS,
        company="Acme Corp",
        job_title="Staff Engineer",
    )
    await start_job_preparation(
        store,
        resume_text="Resume B",
        job_description="JD B",
        analysis_result=_ANALYSIS,
        company="Other Corp",
        job_title="Product Manager",
    )

    response = await client.get(
        "/v1/job-preparations", params={"company": "Acme Corp", "job_title": "Staff Engineer"}
    )

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [str(matching.id)]


async def test_get_returns_404_for_an_unknown_id(api_client_factory) -> None:
    client, _store = await api_client_factory()

    response = await client.get(f"/v1/job-preparations/{uuid4()}")

    assert response.status_code == 404


async def test_get_returns_the_full_persisted_state_for_a_draft_analysis_only_preparation(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="Senior Backend Engineer\nBuild things.",
        analysis_result=_ANALYSIS,
        company="Acme Corp",
    )

    response = await client.get(f"/v1/job-preparations/{job_preparation.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(job_preparation.id)
    assert body["status"] == "active"
    assert body["analysis_result"] == _ANALYSIS
    assert body["career_conversation"] is None
    assert body["tailoring_plan"] is None
    assert body["applied_resume_text"] is None
    assert body["post_apply_analysis"] is None
    assert body["checkpoints"]["initial_analysis_completed_at"] is not None
    assert body["checkpoints"]["career_conversation_completed_at"] is None


async def test_get_returns_every_checkpoint_once_the_full_lifecycle_has_run(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    await record_career_conversation(
        store, job_preparation.id, {"session_id": "s-1", "status": "complete"}
    )
    await record_generated_tailoring_plan(
        store, job_preparation.id, {"plan_id": "plan-1", "suggestions": []}
    )
    await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="SUMMARY\nBackend engineer (tailored).",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )
    await record_post_apply_analysis(
        store,
        job_preparation.id,
        analysis={"overall_assessment": {"overall_score": 85}},
        comparison={"score_before": 70, "score_after": 85, "status": "improved"},
    )

    response = await client.get(f"/v1/job-preparations/{job_preparation.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["career_conversation"] == {"session_id": "s-1", "status": "complete"}
    assert body["tailoring_plan"]["generated_plan"] == {"plan_id": "plan-1", "suggestions": []}
    assert body["applied_resume_text"] == "SUMMARY\nBackend engineer (tailored)."
    assert body["post_apply_analysis"]["comparison"]["status"] == "improved"
    checkpoints = body["checkpoints"]
    assert all(value is not None for value in checkpoints.values())


async def test_get_reflects_apply_succeeded_but_reanalysis_not_yet_run(
    api_client_factory,
) -> None:
    """The exact partial-failure scenario the History feature exists for."""
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    await record_career_conversation(
        store, job_preparation.id, {"session_id": "s-1", "status": "complete"}
    )
    await record_generated_tailoring_plan(
        store, job_preparation.id, {"plan_id": "plan-1", "suggestions": []}
    )
    await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Tailored text",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )
    # Re-analysis never runs (e.g. LLM quota exhausted) -- no call here.

    response = await client.get(f"/v1/job-preparations/{job_preparation.id}")

    body = response.json()
    checkpoints = body["checkpoints"]
    assert checkpoints["initial_analysis_completed_at"] is not None
    assert checkpoints["career_conversation_completed_at"] is not None
    assert checkpoints["tailoring_plan_completed_at"] is not None
    assert checkpoints["applied_at"] is not None
    assert checkpoints["post_apply_analysis_completed_at"] is None
    assert body["post_apply_analysis"] is None
    assert body["applied_resume_text"] == "Tailored text"
