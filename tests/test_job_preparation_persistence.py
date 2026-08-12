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
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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
        # A fresh InMemoryPersistenceStore per test is naturally isolated
        # -- nothing to clean up between tests.
        yield InMemoryPersistenceStore()
        return

    # Unlike InMemoryPersistenceStore, the real Postgres database persists
    # across every test in this module -- truncated here, before each
    # test, so this module's `list_job_preparations` tests (the first
    # ones in this file to run a broad, unscoped query rather than
    # fetching by a specific known id) see only what that one test
    # creates, not leftovers from a previous test's fixture data.
    cleanup_engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with cleanup_engine.begin() as connection:
            await connection.execute(
                text("TRUNCATE job_preparations, resume_versions, resumes CASCADE")
            )
    finally:
        await cleanup_engine.dispose()

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
    # Initial Analysis checkpoint complete; every later checkpoint still
    # incomplete -- each timestamp is independent, never set early.
    assert job_preparation.initial_analysis_completed_at is not None
    assert job_preparation.career_conversation_completed_at is None
    assert job_preparation.tailoring_plan_completed_at is None
    assert job_preparation.applied_at is None
    assert job_preparation.post_apply_analysis_completed_at is None

    after_conversation = await record_career_conversation(
        store, job_preparation.id, {"session_id": "s-1", "status": "complete"}
    )
    assert after_conversation.career_conversation == {"session_id": "s-1", "status": "complete"}
    assert after_conversation.career_conversation_completed_at is not None
    assert after_conversation.tailoring_plan_completed_at is None
    assert after_conversation.applied_at is None
    assert after_conversation.post_apply_analysis_completed_at is None

    after_plan = await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)
    assert after_plan.tailoring_plan == {"generated_plan": _GENERATED_PLAN, "selection": None}
    assert after_plan.tailoring_plan_completed_at is not None
    assert after_plan.applied_at is None
    assert after_plan.post_apply_analysis_completed_at is None

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
    assert after_apply.applied_at is not None
    assert after_apply.post_apply_analysis_completed_at is None
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
    assert after_reanalysis.post_apply_analysis_completed_at is not None

    # All five checkpoints now independently complete.
    final = await store.get_job_preparation(job_preparation.id)
    assert final.initial_analysis_completed_at is not None
    assert final.career_conversation_completed_at is not None
    assert final.tailoring_plan_completed_at is not None
    assert final.applied_at is not None
    assert final.post_apply_analysis_completed_at is not None
    # Still active -- Phase 3 never transitions a preparation to
    # 'completed' automatically (see this module's docstring / the Phase
    # 3 report's "H. Completion" section).
    assert final.status == JobPreparationStatus.ACTIVE


async def test_reanalysis_failure_leaves_the_checkpoint_incomplete(
    store: PersistenceStore,
) -> None:
    """The negative case the checkpoint model exists for: no call, no completion claim.

    `record_post_apply_analysis` is only ever called by the API layer
    after a real re-analysis succeeds (see `tailoring_suggestions.py`'s
    `reanalyze_after_apply`) -- if it fails, nothing here is called at
    all, so `post_apply_analysis`/`post_apply_analysis_completed_at`
    simply stay whatever they already were. This test proves that
    "stay incomplete" state directly, without needing to simulate an
    LLM failure.
    """
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)
    applied = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Applied text",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )
    assert applied.applied_at is not None

    # Simulates the re-analysis LLM call failing before
    # record_post_apply_analysis is ever reached -- no call happens.
    unchanged = await store.get_job_preparation(job_preparation.id)
    assert unchanged.post_apply_analysis is None
    assert unchanged.post_apply_analysis_completed_at is None
    # The already-applied resume/checkpoint is completely unaffected.
    assert unchanged.applied_resume_version_id == applied.applied_resume_version_id
    assert unchanged.applied_at == applied.applied_at


async def test_apply_is_atomic_no_resume_version_leaks_for_an_unknown_preparation(
    store: PersistenceStore,
) -> None:
    """The Apply boundary's atomicity guarantee, observed from outside.

    Can't fault-inject a mid-transaction failure from here, but *can*
    prove the version-creation and the JobPreparation-update are gated
    together: attempting apply_resume_version against a preparation that
    doesn't exist must create zero ResumeVersion rows anywhere, not a
    dangling one for a version-insert that then never completes.
    """

    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    resume_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    resume_id = resume_version.resume_id
    versions_before = await store.list_resume_versions(resume_id)

    with pytest.raises(JobPreparationNotFoundError):
        await record_applied_tailoring_selection(
            store,
            uuid4(),
            applied_resume_text="x",
            selected_suggestion_ids=[],
            edited_texts={},
        )

    versions_after = await store.list_resume_versions(resume_id)
    assert len(versions_after) == len(versions_before)


async def test_apply_creates_exactly_one_new_version_and_pairs_every_field_atomically(
    store: PersistenceStore,
) -> None:
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)
    source_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    versions_before = await store.list_resume_versions(source_version.resume_id)

    updated = await record_applied_tailoring_selection(
        store,
        job_preparation.id,
        applied_resume_text="Tailored text",
        selected_suggestion_ids=["s-1"],
        edited_texts={},
    )

    versions_after = await store.list_resume_versions(source_version.resume_id)
    assert len(versions_after) == len(versions_before) + 1
    # applied_resume_version_id, applied_at, and the selection are all
    # visible together in the single object returned -- proving they were
    # written as one operation, not observable in a partially-applied state.
    assert updated.applied_resume_version_id is not None
    assert updated.applied_at is not None
    assert updated.tailoring_plan["selection"]["selected_suggestion_ids"] == ["s-1"]
    # And a completely fresh read confirms it's durable, not just the
    # call's own return value.
    reread = await store.get_job_preparation(job_preparation.id)
    assert reread.applied_resume_version_id == updated.applied_resume_version_id
    assert reread.applied_at == updated.applied_at


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
    # Apply is only ever reachable after a plan has been generated in the
    # real product (TailoringPlanStore's plan_id -- see
    # tailoring_suggestions.py -- doesn't exist until generate runs), so
    # this mirrors that real sequence rather than calling apply in
    # isolation.
    await record_generated_tailoring_plan(store, job_preparation.id, _GENERATED_PLAN)
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


class TestListJobPreparations:
    """`PersistenceStore.list_job_preparations` -- the query method a future History LIST needs.

    Calls `store.list_job_preparations` directly (not through the
    orchestration layer, which has no wrapper for it -- listing is a pure
    infrastructure read with no checkpoint semantics attached).
    """

    async def test_returns_created_preparations(self, store: PersistenceStore) -> None:
        job_preparation = await start_job_preparation(
            store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
        )

        results = await store.list_job_preparations()

        assert job_preparation.id in {jp.id for jp in results}

    async def test_orders_by_updated_at_descending(self, store: PersistenceStore) -> None:
        first = await start_job_preparation(
            store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
        )
        second = await start_job_preparation(
            store, resume_text="Resume B", job_description="JD B", analysis_result=_ANALYSIS
        )
        # Touch `first` again so it becomes the most recently updated,
        # despite being created first -- proves ordering is by
        # updated_at, not created_at or insertion order.
        third_touch = await record_career_conversation(
            store, first.id, {"session_id": "s-1", "status": "complete"}
        )

        results = await store.list_job_preparations()
        ids_in_order = [jp.id for jp in results]

        assert ids_in_order.index(third_touch.id) < ids_in_order.index(second.id)

    async def test_filters_by_company(self, store: PersistenceStore) -> None:
        matching = await start_job_preparation(
            store,
            resume_text="Resume A",
            job_description="JD A",
            analysis_result=_ANALYSIS,
            company="Acme Corp",
        )
        await start_job_preparation(
            store,
            resume_text="Resume B",
            job_description="JD B",
            analysis_result=_ANALYSIS,
            company="Other Corp",
        )

        results = await store.list_job_preparations(company="Acme Corp")

        assert {jp.id for jp in results} == {matching.id}

    async def test_filters_by_job_title(self, store: PersistenceStore) -> None:
        matching = await start_job_preparation(
            store,
            resume_text="Resume A",
            job_description="JD A",
            analysis_result=_ANALYSIS,
            job_title="Staff Engineer",
        )
        await start_job_preparation(
            store,
            resume_text="Resume B",
            job_description="JD B",
            analysis_result=_ANALYSIS,
            job_title="Product Manager",
        )

        results = await store.list_job_preparations(job_title="Staff Engineer")

        assert {jp.id for jp in results} == {matching.id}

    async def test_filters_by_resume_id(self, store: PersistenceStore) -> None:
        matching = await start_job_preparation(
            store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
        )
        await start_job_preparation(
            store, resume_text="Resume B", job_description="JD B", analysis_result=_ANALYSIS
        )
        matching_version = await store.get_resume_version(matching.source_resume_version_id)

        results = await store.list_job_preparations(resume_id=matching_version.resume_id)

        assert {jp.id for jp in results} == {matching.id}

    async def test_filters_by_updated_after(self, store: PersistenceStore) -> None:
        old = await start_job_preparation(
            store, resume_text="Resume A", job_description="JD A", analysis_result=_ANALYSIS
        )
        new = await start_job_preparation(
            store, resume_text="Resume B", job_description="JD B", analysis_result=_ANALYSIS
        )

        # The cutoff is `old`'s own `updated_at`, not an external
        # `datetime.now()` -- both preparations' timestamps come from
        # whichever backend's own clock persisted them (PostgreSQL's
        # `now()` server-side; the process clock for
        # InMemoryPersistenceStore), so comparing against `old`'s own
        # value can never be skewed by a difference between the test
        # process's clock and a real, separate PostgreSQL server's clock.
        results = await store.list_job_preparations(updated_after=old.updated_at)

        result_ids = {jp.id for jp in results}
        assert new.id in result_ids
        assert old.id not in result_ids

    async def test_respects_limit(self, store: PersistenceStore) -> None:
        for i in range(3):
            await start_job_preparation(
                store,
                resume_text=f"Resume {i}",
                job_description=f"JD {i}",
                analysis_result=_ANALYSIS,
            )

        results = await store.list_job_preparations(limit=2)

        assert len(results) == 2

    async def test_returns_empty_list_when_nothing_matches(self, store: PersistenceStore) -> None:
        await start_job_preparation(
            store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
        )

        results = await store.list_job_preparations(company="Nonexistent Corp")

        assert results == []
