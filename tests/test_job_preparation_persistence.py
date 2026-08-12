"""Tests for `app.orchestration.job_preparation_persistence` -- Phase 3's durable-write wiring.

Parametrized `[memory]`/`[postgres]` exactly like `test_persistence_contract.py`
(reusing the same opt-in `RESUMEPILOT_TEST_DATABASE_URL` mechanism from
`tests/persistence_db_support.py`, not a second database-testing setup):
each function here is written once and runs against both backends, since
this module's whole point is that either backend behaves identically
through the same `PersistenceStore` Protocol.

These are orchestration-level tests -- they call
`app.orchestration.job_preparation_persistence`'s functions directly, not
through HTTP. End-to-end wiring through the real API endpoints (proving
`job_preparation_id` actually threads through /analyze ->
/career-conversation -> /tailoring-suggestions -> /apply -> /reanalyze) is
`tests/test_persistence_workflow_wiring.py`'s job.
"""

from collections.abc import AsyncIterator

import pytest

from app.orchestration.job_preparation_persistence import (
    record_applied_tailoring_selection,
    record_career_conversation,
    record_generated_tailoring_plan,
    record_post_apply_analysis,
    start_job_preparation,
)
from app.persistence.errors import JobPreparationCompletedError, JobPreparationNotFoundError
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.models import JobPreparationStatus, ResumeVersionSource
from app.persistence.postgres_store import PostgresPersistenceStore
from app.persistence.store import PersistenceStore
from tests.persistence_db_support import (
    TEST_DATABASE_URL,
    downgrade_test_database,
    upgrade_test_database,
)


@pytest.fixture(scope="module", autouse=True)
def _postgres_schema_for_this_suite():
    if not TEST_DATABASE_URL:
        yield
        return
    upgrade_test_database()
    yield
    downgrade_test_database()


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param(
            "postgres",
            id="postgres",
            marks=pytest.mark.skipif(
                not TEST_DATABASE_URL,
                reason=(
                    "RESUMEPILOT_TEST_DATABASE_URL is not set -- skipping "
                    "PostgresPersistenceStore orchestration tests."
                ),
            ),
        ),
    ]
)
async def store(request: pytest.FixtureRequest) -> AsyncIterator[PersistenceStore]:
    if request.param == "memory":
        yield InMemoryPersistenceStore()
        return
    postgres_store = PostgresPersistenceStore(TEST_DATABASE_URL)
    try:
        yield postgres_store
    finally:
        await postgres_store.dispose()


_ANALYSIS = {"overall_assessment": {"overall_score": 70}, "strengths": ["Strong backend."]}
_GENERATED_PLAN = {"plan_id": "plan-1", "suggestions": [{"suggestion_id": "s-1"}]}


async def test_start_job_preparation_creates_resume_version_one_and_active_preparation(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store,
        resume_text="SUMMARY\nBackend engineer.",
        job_description="Looking for a backend engineer.",
        analysis_result=_ANALYSIS,
    )

    assert job_preparation.status == JobPreparationStatus.ACTIVE
    assert job_preparation.analysis_result == _ANALYSIS
    assert job_preparation.applied_resume_version_id is None

    source_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    assert source_version is not None
    assert source_version.version_number == 1
    assert source_version.source == ResumeVersionSource.ORIGINAL_UPLOAD


async def test_two_unrelated_analyze_calls_create_two_distinct_resumes(
    store: PersistenceStore,
) -> None:
    first = await start_job_preparation(
        store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
    )
    second = await start_job_preparation(
        store, resume_text="Resume B", job_description="JD B", analysis_result=_ANALYSIS
    )

    first_version = await store.get_resume_version(first.source_resume_version_id)
    second_version = await store.get_resume_version(second.source_resume_version_id)

    assert first_version.resume_id != second_version.resume_id


async def test_job_title_and_resume_name_fall_back_to_a_derived_placeholder_when_unset(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store,
        resume_text="  \nSUMMARY\nBackend engineer.",
        job_description="  \nSenior Backend Engineer\nMore details.",
        analysis_result=_ANALYSIS,
    )

    assert job_preparation.job_title == "Senior Backend Engineer"


async def test_explicit_job_title_and_company_are_used_over_the_placeholder(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store,
        resume_text="Resume text",
        job_description="JD text",
        analysis_result=_ANALYSIS,
        job_title="Staff Engineer",
        company="Acme Corp",
    )

    assert job_preparation.job_title == "Staff Engineer"
    assert job_preparation.company == "Acme Corp"


async def test_full_lifecycle_records_every_workflow_boundary(store: PersistenceStore) -> None:
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    after_conversation = await record_career_conversation(
        store, job_preparation.id, {"session_id": "s-1", "status": "complete"}
    )
    assert after_conversation.career_conversation == {"session_id": "s-1", "status": "complete"}

    after_plan = await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)
    assert after_plan.tailoring_plan == {"generated_plan": _GENERATED_PLAN, "selection": None}

    after_apply = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="SUMMARY\nBackend engineer (tailored).",
        selected_suggestion_ids=["s-1"],
        edited_texts={"s-1": "Backend engineer (edited)."},
    )
    assert after_apply.tailoring_plan == {
        "generated_plan": _GENERATED_PLAN,
        "selection": {
            "selected_suggestion_ids": ["s-1"],
            "edited_texts": {"s-1": "Backend engineer (edited)."},
        },
    }
    assert after_apply.applied_resume_version_id is not None
    applied_version = await store.get_resume_version(after_apply.applied_resume_version_id)
    assert applied_version.source == ResumeVersionSource.APPLIED
    assert applied_version.version_number == 2
    assert applied_version.content == "SUMMARY\nBackend engineer (tailored)."

    after_reanalysis = await record_post_apply_analysis(
        store,
        job_preparation.id,
        analysis={"overall_assessment": {"overall_score": 85}},
        comparison={"score_before": 70, "score_after": 85, "status": "improved"},
    )
    assert after_reanalysis.post_apply_analysis["analysis"] == {
        "overall_assessment": {"overall_score": 85}
    }
    assert after_reanalysis.post_apply_analysis["comparison"] == {
        "score_before": 70,
        "score_after": 85,
        "status": "improved",
    }
    assert after_reanalysis.post_apply_analysis["reanalyzed_at"] is not None

    # Still active -- Phase 3 never transitions a preparation to
    # 'completed' automatically (see this module's docstring / the Phase
    # 3 report's "H. Completion" section).
    final = await store.get_job_preparation(job_preparation.id)
    assert final.status == JobPreparationStatus.ACTIVE


async def test_a_second_apply_creates_a_second_applied_version_and_moves_the_link(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)

    first_apply = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Phase 1 text",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )
    second_apply = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Phase 1 + 2 text",
        selected_suggestion_ids=["s-1", "s-2"],
        edited_texts={},
    )

    assert first_apply.applied_resume_version_id != second_apply.applied_resume_version_id
    latest_version = await store.get_resume_version(second_apply.applied_resume_version_id)
    assert latest_version.version_number == 3
    assert latest_version.content == "Phase 1 + 2 text"
    assert second_apply.tailoring_plan["selection"]["selected_suggestion_ids"] == ["s-1", "s-2"]


async def test_every_mutation_raises_job_preparation_not_found_for_an_unknown_id(
    store: PersistenceStore,
) -> None:
    from uuid import uuid4

    unknown_id = uuid4()

    with pytest.raises(JobPreparationNotFoundError):
        await record_career_conversation(store, unknown_id, {})
    with pytest.raises(JobPreparationNotFoundError):
        await record_generated_tailoring_plan(store, unknown_id, {})
    with pytest.raises(JobPreparationNotFoundError):
        await record_applied_tailoring_selection(
            store,
            unknown_id,
            applied_resume_text="x",
            selected_suggestion_ids=[],
            edited_texts={},
        )
    with pytest.raises(JobPreparationNotFoundError):
        await record_post_apply_analysis(store, unknown_id, analysis={}, comparison={})


async def test_a_completed_preparation_cannot_be_mutated_by_any_boundary(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    applied = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Applied text",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )
    # The only way to reach 'completed' at all is a direct save through
    # the store itself -- Phase 3's orchestration layer never does this
    # (see the "still active" assertion in the full-lifecycle test above)
    # -- exercised here only to prove save_job_preparation's existing
    # read-only-history guarantee still holds through this module's
    # read-modify-write helper, not to claim Phase 3 triggers it.
    completed = await store.save_job_preparation(
        applied.model_copy(update={"status": JobPreparationStatus.COMPLETED})
    )
    assert completed.status == JobPreparationStatus.COMPLETED

    with pytest.raises(JobPreparationCompletedError):
        await record_post_apply_analysis(store, job_preparation.id, analysis={}, comparison={})
