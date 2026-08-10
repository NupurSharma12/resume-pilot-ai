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
            }
        )
    )

    assert updated.status == JobPreparationStatus.ACTIVE
    assert updated.analysis_result == {"overall_assessment": {"overall_score": 72}}
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
                "post_apply_analysis": post_apply_analysis,
            }
        )
    )

    assert updated.tailoring_plan == tailoring_plan
    assert updated.post_apply_analysis == post_apply_analysis
    # And it survives a completely fresh read, not just the save's own return value.
    reread = await store.get_job_preparation(preparation.id)
    assert reread.tailoring_plan == tailoring_plan
    assert reread.post_apply_analysis == post_apply_analysis
