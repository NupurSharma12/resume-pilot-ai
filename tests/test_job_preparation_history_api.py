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
        settings = Settings(
            log_json=False, gemini_api_key="test-gemini-api-key", persistence_backend="memory"
        )
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
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


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


async def test_list_supports_case_insensitive_search_across_job_title_and_company(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    matching = await start_job_preparation(
        store,
        resume_text="Resume A",
        job_description="JD A",
        analysis_result=_ANALYSIS,
        company="Acme Corp",
        job_title="Staff Backend Engineer",
    )
    also_matching = await start_job_preparation(
        store,
        resume_text="Resume B",
        job_description="JD B",
        analysis_result=_ANALYSIS,
        company="Backend Solutions Inc",
        job_title="Product Manager",
    )
    await start_job_preparation(
        store,
        resume_text="Resume C",
        job_description="JD C",
        analysis_result=_ANALYSIS,
        company="Other Corp",
        job_title="Frontend Engineer",
    )

    response = await client.get("/v1/job-preparations", params={"search": "BACKEND"})

    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(matching.id), str(also_matching.id)}


async def test_list_search_ignores_leading_trailing_whitespace(api_client_factory) -> None:
    client, store = await api_client_factory()
    matching = await start_job_preparation(
        store,
        resume_text="Resume A",
        job_description="JD A",
        analysis_result=_ANALYSIS,
        job_title="Staff Engineer",
    )

    response = await client.get("/v1/job-preparations", params={"search": "  staff  "})

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [str(matching.id)]


async def test_list_blank_search_behaves_like_no_search(api_client_factory) -> None:
    client, store = await api_client_factory()
    await start_job_preparation(
        store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
    )

    response = await client.get("/v1/job-preparations", params={"search": "   "})

    assert len(response.json()["items"]) == 1


async def test_list_pagination_returns_the_requested_page_and_the_true_total(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    created = []
    for i in range(5):
        jp = await start_job_preparation(
            store,
            resume_text=f"Resume {i}",
            job_description=f"JD {i}",
            analysis_result=_ANALYSIS,
            job_title=f"Role {i}",
        )
        created.append(jp)
    expected_order = list(reversed(created))  # newest-updated first

    first_page = await client.get("/v1/job-preparations", params={"limit": 2, "offset": 0})
    second_page = await client.get("/v1/job-preparations", params={"limit": 2, "offset": 2})

    first_body = first_page.json()
    assert [item["id"] for item in first_body["items"]] == [
        str(jp.id) for jp in expected_order[0:2]
    ]
    # `total` reflects every matching preparation, not just this page's size.
    assert first_body["total"] == 5
    assert first_body["limit"] == 2
    assert first_body["offset"] == 0

    second_body = second_page.json()
    assert [item["id"] for item in second_body["items"]] == [
        str(jp.id) for jp in expected_order[2:4]
    ]
    assert second_body["total"] == 5
    assert second_body["offset"] == 2


async def test_list_rejects_a_negative_offset(api_client_factory) -> None:
    client, _store = await api_client_factory()

    response = await client.get("/v1/job-preparations", params={"offset": -1})

    assert response.status_code == 422


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
    assert body["resume_text"] == "SUMMARY\nBackend engineer."
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


# ---- History Test Isolation & Delete ------------------------------------


async def test_list_excludes_a_preparation_with_include_in_history_false(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    await start_job_preparation(
        store,
        resume_text="E2E test resume.",
        job_description="E2E test JD.",
        analysis_result=_ANALYSIS,
        include_in_history=False,
    )

    response = await client.get("/v1/job-preparations")

    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_list_includes_a_normal_preparation_alongside_an_excluded_one(
    api_client_factory,
) -> None:
    client, store = await api_client_factory()
    real = await start_job_preparation(
        store,
        resume_text="Real resume.",
        job_description="Real JD.",
        analysis_result=_ANALYSIS,
    )
    await start_job_preparation(
        store,
        resume_text="E2E test resume.",
        job_description="E2E test JD.",
        analysis_result=_ANALYSIS,
        include_in_history=False,
    )

    response = await client.get("/v1/job-preparations")

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [str(real.id)]


async def test_get_returns_a_test_only_preparation_directly_by_id(api_client_factory) -> None:
    """A test-only preparation is still fully addressable by id -- only hidden from the list."""
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store,
        resume_text="E2E test resume.",
        job_description="E2E test JD.",
        analysis_result=_ANALYSIS,
        include_in_history=False,
    )

    response = await client.get(f"/v1/job-preparations/{job_preparation.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(job_preparation.id)


async def test_delete_removes_a_preparation_from_the_list(api_client_factory) -> None:
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    delete_response = await client.delete(f"/v1/job-preparations/{job_preparation.id}")

    assert delete_response.status_code == 204
    list_response = await client.get("/v1/job-preparations")
    assert list_response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_delete_does_not_remove_the_row_get_by_id_still_returns_it(
    api_client_factory,
) -> None:
    """Chosen behavior: `GET .../{id}` still returns a soft-deleted preparation -- see that

    endpoint's own docstring for why (a direct-by-id lookup is a
    different operation from History's listing).
    """
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    await client.delete(f"/v1/job-preparations/{job_preparation.id}")
    response = await client.get(f"/v1/job-preparations/{job_preparation.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(job_preparation.id)


async def test_delete_for_an_unknown_id_returns_404(api_client_factory) -> None:
    client, _store = await api_client_factory()

    response = await client.delete(f"/v1/job-preparations/{uuid4()}")

    assert response.status_code == 404


async def test_delete_is_idempotent_for_an_already_deleted_preparation(api_client_factory) -> None:
    client, store = await api_client_factory()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    first = await client.delete(f"/v1/job-preparations/{job_preparation.id}")
    second = await client.delete(f"/v1/job-preparations/{job_preparation.id}")

    assert first.status_code == 204
    assert second.status_code == 204
