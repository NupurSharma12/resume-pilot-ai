"""Shared behavioral contract tests for `PersistenceStore` implementations.

Every test function below is written once, against the `store` fixture,
and runs against **both** `InMemoryPersistenceStore` and
`PostgresPersistenceStore` (parametrized as `[memory]`/`[postgres]` test
ids) -- the same test bodies, not two hand-maintained copies. The
`postgres` parametrization is skipped cleanly when
`RESUMEPILOT_TEST_DATABASE_URL` is unset, exactly like this project's
existing opt-in database-test mechanism from Phase 1 (see
`tests/persistence_db_support.py`, reused here rather than building a
second database-testing setup).

`PersistenceStore` is an `async def` Protocol (see `app.persistence.store`),
so every test here is `async def` and `await`s the store directly --
this project's established convention, `asyncio_mode = "auto"`
(pyproject.toml), auto-detects both async test functions and async
fixtures with no extra decorator.

These tests assert **domain behavior only** -- return types, error types,
and observable field values -- never SQLAlchemy/ORM/row internals. Schema-
level verification (columns, constraints, indexes existing in the actual
database) is `test_persistence_db_metadata.py`/
`test_persistence_db_migration_integration.py`'s job, not this file's.

Two things are deliberately *not* covered here, because they aren't part
of the `PersistenceStore` contract itself:

- A true concurrent-race duplicate `version_number` (translated to
  `ConcurrentResumeVersionConflictError`) can't happen in
  `InMemoryPersistenceStore` by construction (single-process, GIL-
  serialized dict mutation) -- there's no shared behavior to assert here.
  See `test_persistence_postgres_integration.py` for that, PostgreSQL-only.
- "Two store instances never share state" is an implementation detail of
  `InMemoryPersistenceStore` (see `test_persistence_memory_store.py`),
  not a promise the Protocol makes -- two `PostgresPersistenceStore`
  instances pointed at the same database are *supposed* to share state,
  since that's the entire point of a durable, shared backend.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from app.persistence.errors import (
    InvalidJobPreparationStatusError,
    InvalidResumeVersionSourceError,
    JobPreparationCompletedError,
    JobPreparationNotFoundError,
    ResumeNotFoundError,
    ResumeVersionNotFoundError,
)
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.models import JobPreparationStatus, ResumeVersionSource
from app.persistence.postgres_store import PostgresPersistenceStore
from app.persistence.store import PersistenceStore
from tests.persistence_db_support import (
    TEST_DATABASE_URL,
    downgrade_test_database,
    upgrade_test_database,
)


@pytest.fixture(scope="session", autouse=True)
def _postgres_schema_for_contract_suite():
    """Migrate `RESUMEPILOT_TEST_DATABASE_URL` to `head` once for this whole test module.

    A no-op (and instant) when the variable is unset -- every `postgres`
    parametrization below is independently skipped in that case, so there
    would be nothing to migrate for anyway. `upgrade_test_database`/
    `downgrade_test_database` each scope `RESUMEPILOT_DATABASE_URL` tightly
    around just their own Alembic call (see `persistence_db_support.py`),
    not across this fixture's whole session-long `yield` -- so it never
    leaks into an unrelated test that happens to run in between.
    """
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
                    "PostgresPersistenceStore contract tests."
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
        # Each test gets its own store (and thus its own connection
        # pool) -- disposing it here is what makes that safe to do once
        # per test rather than leaking pooled connections across the
        # whole session. See PostgresPersistenceStore's module docstring.
        await postgres_store.dispose()


async def _seed_resume_version(store: PersistenceStore, content: str = "Original resume text"):
    """Create a resume plus its (required) first, original_upload version."""
    resume = await store.create_resume(name="Alice's resume")
    version = await store.create_resume_version(
        resume.id, content=content, source=ResumeVersionSource.ORIGINAL_UPLOAD
    )
    return resume, version


# ---- Resumes -----------------------------------------------------------


async def test_create_resume_returns_a_resume_with_the_given_name(
    store: PersistenceStore,
) -> None:
    resume = await store.create_resume(name="Alice's resume")

    assert resume.name == "Alice's resume"
    assert resume.created_at == resume.updated_at


async def test_get_resume_retrieves_the_created_resume(store: PersistenceStore) -> None:
    created = await store.create_resume(name="Alice's resume")

    fetched = await store.get_resume(created.id)

    assert fetched == created


async def test_get_resume_returns_none_for_an_unknown_id(store: PersistenceStore) -> None:
    assert await store.get_resume(uuid.uuid4()) is None


async def test_two_uploads_of_the_same_name_are_two_distinct_resumes(
    store: PersistenceStore,
) -> None:
    # Rule: an uploaded resume never re-identifies an existing one -- not
    # even by matching name.
    first = await store.create_resume(name="Resume.pdf")
    second = await store.create_resume(name="Resume.pdf")

    assert first.id != second.id


# ---- Resume versions -----------------------------------------------------


async def test_first_version_is_original_upload_numbered_one(store: PersistenceStore) -> None:
    resume, version = await _seed_resume_version(store)

    assert version.version_number == 1
    assert version.resume_id == resume.id
    assert version.source == ResumeVersionSource.ORIGINAL_UPLOAD
    assert version.content == "Original resume text"


async def test_get_resume_version_retrieves_the_created_version(store: PersistenceStore) -> None:
    _resume, created = await _seed_resume_version(store)

    fetched = await store.get_resume_version(created.id)

    assert fetched == created


async def test_get_resume_version_returns_none_for_an_unknown_id(
    store: PersistenceStore,
) -> None:
    assert await store.get_resume_version(uuid.uuid4()) is None


async def test_create_resume_version_for_an_unknown_resume_raises(
    store: PersistenceStore,
) -> None:
    with pytest.raises(ResumeNotFoundError):
        await store.create_resume_version(
            uuid.uuid4(), content="text", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )


async def test_second_version_cannot_be_original_upload(store: PersistenceStore) -> None:
    resume, _v1 = await _seed_resume_version(store)

    with pytest.raises(InvalidResumeVersionSourceError):
        await store.create_resume_version(
            resume.id, content="v2", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )


async def test_first_version_cannot_be_applied(store: PersistenceStore) -> None:
    resume = await store.create_resume(name="Alice's resume")

    with pytest.raises(InvalidResumeVersionSourceError):
        await store.create_resume_version(
            resume.id, content="v1", source=ResumeVersionSource.APPLIED
        )


async def test_applied_version_after_original_upload_succeeds(store: PersistenceStore) -> None:
    resume, _v1 = await _seed_resume_version(store)

    v2 = await store.create_resume_version(
        resume.id, content="Tailored text", source=ResumeVersionSource.APPLIED
    )

    assert v2.version_number == 2
    assert v2.source == ResumeVersionSource.APPLIED


async def test_version_numbers_increment_sequentially_per_resume(store: PersistenceStore) -> None:
    resume, v1 = await _seed_resume_version(store)
    v2 = await store.create_resume_version(
        resume.id, content="v2", source=ResumeVersionSource.APPLIED
    )
    v3 = await store.create_resume_version(
        resume.id, content="v3", source=ResumeVersionSource.APPLIED
    )

    assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]


async def test_version_numbering_is_independent_per_resume(store: PersistenceStore) -> None:
    resume_a, a_v1 = await _seed_resume_version(store, content="a-v1")
    resume_b, b_v1 = await _seed_resume_version(store, content="b-v1")

    assert a_v1.version_number == 1
    assert b_v1.version_number == 1
    assert resume_a.id != resume_b.id


async def test_list_resume_versions_returns_every_version_in_order(
    store: PersistenceStore,
) -> None:
    resume, v1 = await _seed_resume_version(store)
    v2 = await store.create_resume_version(
        resume.id, content="v2", source=ResumeVersionSource.APPLIED
    )

    versions = await store.list_resume_versions(resume.id)

    assert [v.id for v in versions] == [v1.id, v2.id]


async def test_list_resume_versions_returns_empty_list_for_an_unknown_resume(
    store: PersistenceStore,
) -> None:
    assert await store.list_resume_versions(uuid.uuid4()) == []


# ---- Job preparations ------------------------------------------------------


async def test_create_job_preparation_starts_in_draft_with_no_applied_version(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)

    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company="Acme",
    )

    assert preparation.status == JobPreparationStatus.DRAFT
    assert preparation.source_resume_version_id == version.id
    assert preparation.applied_resume_version_id is None
    assert preparation.company == "Acme"
    assert preparation.analysis_result is None
    assert preparation.tailoring_plan is None
    assert preparation.created_at == preparation.updated_at


async def test_create_job_preparation_for_an_unknown_resume_version_raises(
    store: PersistenceStore,
) -> None:
    with pytest.raises(ResumeVersionNotFoundError):
        await store.create_job_preparation(
            source_resume_version_id=uuid.uuid4(),
            job_title="Backend Engineer",
            job_description="Build things.",
        )


async def test_get_job_preparation_retrieves_the_created_preparation(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    created = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    assert await store.get_job_preparation(created.id) == created


async def test_get_job_preparation_returns_none_for_an_unknown_id(
    store: PersistenceStore,
) -> None:
    assert await store.get_job_preparation(uuid.uuid4()) is None


async def test_save_job_preparation_persists_updated_fields(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    updated = await store.save_job_preparation(
        preparation.model_copy(
            update={
                "status": JobPreparationStatus.ACTIVE,
                "analysis_result": {"overall_assessment": {"overall_score": 72}},
                "initial_analysis_completed_at": datetime.now(UTC),
            }
        )
    )

    assert updated.status == JobPreparationStatus.ACTIVE
    assert updated.analysis_result == {"overall_assessment": {"overall_score": 72}}
    assert updated.initial_analysis_completed_at is not None
    assert await store.get_job_preparation(preparation.id) == updated


async def test_save_job_preparation_bumps_updated_at(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    updated = await store.save_job_preparation(
        preparation.model_copy(update={"status": JobPreparationStatus.ACTIVE})
    )

    assert updated.updated_at >= preparation.updated_at
    assert updated.created_at == preparation.created_at


async def test_save_job_preparation_for_an_unknown_id_raises(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    created = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )
    phantom = created.model_copy(update={"id": uuid.uuid4()})

    with pytest.raises(JobPreparationNotFoundError):
        await store.save_job_preparation(phantom)


async def test_save_job_preparation_with_unknown_applied_version_raises(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    with pytest.raises(ResumeVersionNotFoundError):
        await store.save_job_preparation(
            preparation.model_copy(update={"applied_resume_version_id": uuid.uuid4()})
        )


async def test_completed_status_requires_an_applied_resume_version(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    with pytest.raises(InvalidJobPreparationStatusError):
        await store.save_job_preparation(
            preparation.model_copy(update={"status": JobPreparationStatus.COMPLETED})
        )


async def test_draft_to_active_to_completed_lifecycle(store: PersistenceStore) -> None:
    resume, original = await _seed_resume_version(store)
    applied = await store.create_resume_version(
        resume.id, content="Tailored text", source=ResumeVersionSource.APPLIED
    )
    preparation = await store.create_job_preparation(
        source_resume_version_id=original.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )
    assert preparation.status == JobPreparationStatus.DRAFT

    active = await store.save_job_preparation(
        preparation.model_copy(update={"status": JobPreparationStatus.ACTIVE})
    )
    assert active.status == JobPreparationStatus.ACTIVE

    completed = await store.save_job_preparation(
        active.model_copy(
            update={
                "status": JobPreparationStatus.COMPLETED,
                "applied_resume_version_id": applied.id,
                "applied_at": datetime.now(UTC),
            }
        )
    )
    assert completed.status == JobPreparationStatus.COMPLETED
    assert completed.applied_resume_version_id == applied.id


async def test_completed_preparation_cannot_be_saved_again(store: PersistenceStore) -> None:
    resume, original = await _seed_resume_version(store)
    applied = await store.create_resume_version(
        resume.id, content="Tailored text", source=ResumeVersionSource.APPLIED
    )
    preparation = await store.create_job_preparation(
        source_resume_version_id=original.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )
    completed = await store.save_job_preparation(
        preparation.model_copy(
            update={
                "status": JobPreparationStatus.COMPLETED,
                "applied_resume_version_id": applied.id,
                "applied_at": datetime.now(UTC),
            }
        )
    )

    with pytest.raises(JobPreparationCompletedError):
        await store.save_job_preparation(
            completed.model_copy(update={"job_title": "Senior Backend Engineer"})
        )

    # The rejected write must not have partially applied.
    refetched = await store.get_job_preparation(preparation.id)
    assert refetched.job_title == "Backend Engineer"


async def test_json_fields_round_trip_nested_structures_faithfully(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )
    tailoring_plan = {
        "generated_plan": {
            "plan_id": "plan-1",
            "suggestions": [
                {"suggestion_id": "s1", "confidence": 87, "evidence_ids": ["e1", "e2"]}
            ],
        },
        "selection": {
            "selected_suggestion_ids": ["s1"],
            "edited_texts": {"s1": 'A user-edited replacement, with "quotes" and a newline\n.'},
        },
    }
    post_apply_analysis = {
        "analysis": {"overall_assessment": {"overall_score": 81}},
        "comparison": {"score_before": 70, "score_after": 81, "score_delta": 11},
        "reanalyzed_at": "2026-08-10T00:00:00+00:00",
    }

    updated = await store.save_job_preparation(
        preparation.model_copy(
            update={
                "tailoring_plan": tailoring_plan,
                "tailoring_plan_completed_at": datetime.now(UTC),
                "post_apply_analysis": post_apply_analysis,
                "post_apply_analysis_completed_at": datetime.now(UTC),
            }
        )
    )

    assert updated.tailoring_plan == tailoring_plan
    assert updated.post_apply_analysis == post_apply_analysis
    # And it survives a completely fresh read, not just the save's own return value.
    reread = await store.get_job_preparation(preparation.id)
    assert reread.tailoring_plan == tailoring_plan
    assert reread.post_apply_analysis == post_apply_analysis


# ---- History Test Isolation & Delete ------------------------------------


async def test_create_job_preparation_defaults_to_included_in_history(
    store: PersistenceStore,
) -> None:
    """The safe default: every real caller that doesn't pass `include_in_history` is visible."""
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"

    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=company,
    )

    assert preparation.include_in_history is True
    assert preparation.deleted_at is None
    # Scoped by a unique `company` (not asserting the listing is empty
    # otherwise) -- a real, shared PostgresPersistenceStore accumulates
    # rows from every other test in this session, unlike a fresh
    # InMemoryPersistenceStore per test; `company`/`job_title` are the
    # same plain-column filters `list_job_preparations` already supports
    # for exactly this kind of scoping (see its own docstring).
    assert [jp.id for jp in await store.list_job_preparations(company=company)] == [preparation.id]


async def test_create_job_preparation_with_include_in_history_false_is_excluded_from_listing(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"

    test_preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="E2E Test Preparation",
        job_description="Build things.",
        company=company,
        include_in_history=False,
    )

    assert test_preparation.include_in_history is False
    assert await store.list_job_preparations(company=company) == []
    # Still fully persisted and addressable by id -- only excluded from the listing.
    assert await store.get_job_preparation(test_preparation.id) == test_preparation


async def test_list_job_preparations_mixes_history_and_test_preparations_correctly(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    real = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Real Preparation",
        job_description="Build things.",
        company=company,
    )
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Test Preparation",
        job_description="Build things.",
        company=company,
        include_in_history=False,
    )

    assert [jp.id for jp in await store.list_job_preparations(company=company)] == [real.id]


async def test_soft_delete_removes_a_preparation_from_the_listing(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=company,
    )
    assert [jp.id for jp in await store.list_job_preparations(company=company)] == [preparation.id]

    deleted = await store.soft_delete_job_preparation(preparation.id)

    assert deleted.deleted_at is not None
    assert await store.list_job_preparations(company=company) == []


async def test_soft_delete_does_not_remove_the_row_itself(store: PersistenceStore) -> None:
    """`get_job_preparation` is unaffected by soft-delete -- only the listing is."""
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    await store.soft_delete_job_preparation(preparation.id)

    reread = await store.get_job_preparation(preparation.id)
    assert reread is not None
    assert reread.deleted_at is not None
    assert reread.job_title == "Backend Engineer"


async def test_soft_delete_is_idempotent(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    preparation = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
    )

    first = await store.soft_delete_job_preparation(preparation.id)
    second = await store.soft_delete_job_preparation(preparation.id)

    assert first.deleted_at is not None
    assert second.deleted_at is not None


async def test_soft_delete_for_an_unknown_id_raises(store: PersistenceStore) -> None:
    with pytest.raises(JobPreparationNotFoundError):
        await store.soft_delete_job_preparation(uuid.uuid4())


# ---- list_job_preparations: offset pagination / search / count_job_preparations ----


async def test_offset_skips_the_given_number_of_newest_first_results(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    # Created in order -- `list_job_preparations` sorts newest-`updated_at`-first, so this
    # list is expected back in reverse creation order.
    created = [
        await store.create_job_preparation(
            source_resume_version_id=version.id,
            job_title=f"Role {i}",
            job_description="Build things.",
            company=company,
        )
        for i in range(5)
    ]
    expected_order = list(reversed(created))

    first_page = await store.list_job_preparations(company=company, limit=2, offset=0)
    second_page = await store.list_job_preparations(company=company, limit=2, offset=2)
    third_page = await store.list_job_preparations(company=company, limit=2, offset=4)
    past_the_end = await store.list_job_preparations(company=company, limit=2, offset=10)

    assert [jp.id for jp in first_page] == [jp.id for jp in expected_order[0:2]]
    assert [jp.id for jp in second_page] == [jp.id for jp in expected_order[2:4]]
    assert [jp.id for jp in third_page] == [jp.id for jp in expected_order[4:5]]
    assert past_the_end == []


async def test_search_matches_job_title_case_insensitively(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    match = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Senior Backend Engineer",
        job_description="Build things.",
        company=company,
    )
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Product Manager",
        job_description="Build things.",
        company=company,
    )

    results = await store.list_job_preparations(company=company, search="BACKEND")

    assert [jp.id for jp in results] == [match.id]


async def test_search_matches_company_case_insensitively(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    unique = str(uuid.uuid4())
    match = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=f"Initech-{unique}",
    )
    other = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=f"Acme-{unique}",
    )

    results = await store.list_job_preparations(search=f"initech-{unique}".lower())

    result_ids = {jp.id for jp in results}
    assert match.id in result_ids
    assert other.id not in result_ids


async def test_search_matches_the_resume_name(store: PersistenceStore) -> None:
    unique = str(uuid.uuid4())
    resume = await store.create_resume(name=f"Distinctive Resume Name {unique}")
    version = await store.create_resume_version(
        resume.id, content="Resume text.", source=ResumeVersionSource.ORIGINAL_UPLOAD
    )
    company = f"Acme-{uuid.uuid4()}"
    match = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=company,
    )

    results = await store.list_job_preparations(company=company, search=unique)

    assert [jp.id for jp in results] == [match.id]


async def test_search_with_no_match_returns_empty(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=company,
    )

    results = await store.list_job_preparations(
        company=company, search=f"nonexistent-{uuid.uuid4()}"
    )

    assert results == []


async def test_count_job_preparations_matches_the_same_filters_as_list(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    for i in range(3):
        await store.create_job_preparation(
            source_resume_version_id=version.id,
            job_title=f"Role {i}",
            job_description="Build things.",
            company=company,
        )

    total = await store.count_job_preparations(company=company)
    # A `limit` smaller than the total still reports the *total* count,
    # not the page size -- the whole point of a separate count.
    page = await store.list_job_preparations(company=company, limit=1)

    assert total == 3
    assert len(page) == 1


async def test_count_job_preparations_excludes_test_only_and_soft_deleted(
    store: PersistenceStore,
) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    counted = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Backend Engineer",
        job_description="Build things.",
        company=company,
    )
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Excluded Test Preparation",
        job_description="Build things.",
        company=company,
        include_in_history=False,
    )
    to_delete = await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Soon Deleted",
        job_description="Build things.",
        company=company,
    )
    await store.soft_delete_job_preparation(to_delete.id)

    assert await store.count_job_preparations(company=company) == 1
    assert [jp.id for jp in await store.list_job_preparations(company=company)] == [counted.id]


async def test_count_job_preparations_respects_search(store: PersistenceStore) -> None:
    _resume, version = await _seed_resume_version(store)
    company = f"Acme-{uuid.uuid4()}"
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Senior Backend Engineer",
        job_description="Build things.",
        company=company,
    )
    await store.create_job_preparation(
        source_resume_version_id=version.id,
        job_title="Product Manager",
        job_description="Build things.",
        company=company,
    )

    assert await store.count_job_preparations(company=company, search="backend") == 1
    assert await store.count_job_preparations(company=company) == 2
