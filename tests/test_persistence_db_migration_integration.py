"""Integration tests: run the real Alembic migration against a real PostgreSQL database.

Deliberately separate from `test_persistence_db_metadata.py` (pure,
always-on metadata assertions) rather than a fake/in-process PostgreSQL
stand-in -- per this phase's explicit instruction not to invent a fake
PostgreSQL implementation. This whole module is skipped unless
`RESUMEPILOT_TEST_DATABASE_URL` is set to a real, disposable PostgreSQL
database -- never the application's own `RESUMEPILOT_DATABASE_URL`, so
running the ordinary test suite can never accidentally reach a real
(e.g. Neon) database a developer happens to have configured for the app
itself. A local throwaway instance works fine, e.g.:

    docker run --rm -d -p 55432:5432 -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=resumepilot_test postgres:16-alpine
    export RESUMEPILOT_TEST_DATABASE_URL="postgresql+asyncpg://postgres:test@localhost:55432/resumepilot_test"
    uv run pytest tests/test_persistence_db_migration_integration.py

Every test upgrades to `head`, asserts against the real database via
`sqlalchemy.inspect`, then downgrades back to `base` in a `finally` --
so the target database is left empty regardless of pass/fail, and the
suite is safe to run repeatedly against the same disposable instance.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.persistence.db.tables import ResumeRow
from tests.persistence_db_support import (
    TEST_DATABASE_URL,
    check_test_database,
    downgrade_test_database,
    upgrade_test_database,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "RESUMEPILOT_TEST_DATABASE_URL is not set -- skipping migration integration tests. "
        "See this module's docstring for how to run them against a local PostgreSQL instance."
    ),
)


@pytest.fixture
def migrated_database() -> str:
    """Run `alembic upgrade head` against `RESUMEPILOT_TEST_DATABASE_URL`, then tear down.

    `upgrade_test_database`/`downgrade_test_database` (see
    `tests/persistence_db_support.py`) each point `RESUMEPILOT_DATABASE_URL`
    at the test database only for the duration of their own Alembic call
    -- never held open for this whole fixture, let alone the test session,
    which would leak a real-looking value into unrelated tests.
    """
    assert (
        TEST_DATABASE_URL is not None
    )  # narrows for type-checkers; skipif already guarantees this

    upgrade_test_database()
    try:
        yield TEST_DATABASE_URL
    finally:
        downgrade_test_database()


async def _reflect(url: str) -> dict:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:

            def _inspect(sync_connection):
                insp = inspect(sync_connection)
                return {
                    "table_names": set(insp.get_table_names()),
                    "resumes": {
                        "columns": {c["name"]: c for c in insp.get_columns("resumes")},
                    },
                    "resume_versions": {
                        "columns": {c["name"]: c for c in insp.get_columns("resume_versions")},
                        "foreign_keys": insp.get_foreign_keys("resume_versions"),
                        "unique_constraints": insp.get_unique_constraints("resume_versions"),
                        "check_constraints": insp.get_check_constraints("resume_versions"),
                    },
                    "job_preparations": {
                        "columns": {c["name"]: c for c in insp.get_columns("job_preparations")},
                        "foreign_keys": insp.get_foreign_keys("job_preparations"),
                        "check_constraints": insp.get_check_constraints("job_preparations"),
                        "indexes": insp.get_indexes("job_preparations"),
                    },
                }

            return await connection.run_sync(_inspect)
    finally:
        await engine.dispose()


def test_migration_creates_exactly_the_three_frozen_tables(migrated_database: str) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    # alembic_version is Alembic's own bookkeeping table, expected alongside ours.
    assert schema["table_names"] == {
        "resumes",
        "resume_versions",
        "job_preparations",
        "alembic_version",
    }


def test_resume_versions_foreign_key_is_on_delete_restrict(migrated_database: str) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    (fk,) = schema["resume_versions"]["foreign_keys"]
    assert fk["referred_table"] == "resumes"
    assert fk["options"].get("ondelete") == "RESTRICT"


def test_job_preparations_foreign_keys_are_on_delete_restrict(migrated_database: str) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    fks = schema["job_preparations"]["foreign_keys"]
    assert len(fks) == 2
    for fk in fks:
        assert fk["referred_table"] == "resume_versions"
        assert fk["options"].get("ondelete") == "RESTRICT"


def test_job_preparations_has_both_agreed_indexes(migrated_database: str) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    indexed_columns = {
        tuple(index["column_names"]) for index in schema["job_preparations"]["indexes"]
    }
    assert ("source_resume_version_id",) in indexed_columns
    assert ("applied_resume_version_id",) in indexed_columns


def test_check_constraints_are_present_on_both_tables(migrated_database: str) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    version_check_names = {c["name"] for c in schema["resume_versions"]["check_constraints"]}
    assert "ck_resume_versions_version_number_positive" in version_check_names
    assert "ck_resume_versions_original_upload_is_version_one" in version_check_names
    assert "ck_resume_versions_source_allowed_values" in version_check_names

    prep_check_names = {c["name"] for c in schema["job_preparations"]["check_constraints"]}
    assert "ck_job_preparations_completed_requires_applied_version" in prep_check_names
    assert "ck_job_preparations_status_allowed_values" in prep_check_names
    assert "ck_job_preparations_initial_analysis_checkpoint_consistent" in prep_check_names
    assert "ck_job_preparations_career_conversation_checkpoint_consistent" in prep_check_names
    assert "ck_job_preparations_tailoring_plan_checkpoint_consistent" in prep_check_names
    assert "ck_job_preparations_applied_checkpoint_consistent" in prep_check_names
    assert "ck_job_preparations_post_apply_analysis_checkpoint_consistent" in prep_check_names


def test_job_preparations_has_the_five_checkpoint_timestamp_columns(
    migrated_database: str,
) -> None:
    schema = asyncio.run(_reflect(migrated_database))

    columns = schema["job_preparations"]["columns"]
    for column_name in (
        "initial_analysis_completed_at",
        "career_conversation_completed_at",
        "tailoring_plan_completed_at",
        "applied_at",
        "post_apply_analysis_completed_at",
    ):
        assert column_name in columns, column_name
        assert columns[column_name]["nullable"] is True, column_name


def test_checkpoint_consistency_constraint_rejects_a_payload_without_its_timestamp(
    migrated_database: str,
) -> None:
    """The DB-level safety net: a payload can never be stored without its paired timestamp.

    Exercises the real constraint against the real database with a raw
    SQLAlchemy Core insert -- deliberately bypassing
    `PostgresPersistenceStore` (which always pairs them correctly) to
    prove the constraint itself, not just the application code that
    happens to respect it, is what prevents an inconsistent checkpoint.
    """
    from sqlalchemy.exc import IntegrityError

    from app.persistence.db.tables import JobPreparationRow, ResumeRow, ResumeVersionRow

    async def _attempt_inconsistent_insert() -> bool:
        engine = create_async_engine(migrated_database)
        try:
            resume_id = uuid.uuid4()
            version_id = uuid.uuid4()
            async with engine.begin() as connection:
                await connection.execute(
                    ResumeRow.__table__.insert().values(id=resume_id, name="Alice")
                )
                await connection.execute(
                    ResumeVersionRow.__table__.insert().values(
                        id=version_id,
                        resume_id=resume_id,
                        version_number=1,
                        content="Original resume text",
                        source="original_upload",
                    )
                )
            try:
                async with engine.begin() as connection:
                    # analysis_result set, but initial_analysis_completed_at
                    # left null -- exactly the inconsistent state the
                    # checkpoint model must never allow.
                    await connection.execute(
                        JobPreparationRow.__table__.insert().values(
                            id=uuid.uuid4(),
                            source_resume_version_id=version_id,
                            job_title="Backend Engineer",
                            job_description="Build things.",
                            analysis_result={"overall_assessment": {"overall_score": 70}},
                            initial_analysis_completed_at=None,
                            status="active",
                        )
                    )
                return False
            except IntegrityError:
                return True
        finally:
            await engine.dispose()

    rejected = asyncio.run(_attempt_inconsistent_insert())
    assert rejected is True


async def _insert_and_bump(url: str) -> tuple:
    """Insert a resume, then update it in a later transaction, returning both timestamp pairs.

    Deliberately two separate transactions (two `engine.begin()` blocks),
    not one: PostgreSQL's `now()` -- what both `server_default` and
    `onupdate` render to -- is stable for the lifetime of one transaction,
    so an insert and update sharing a transaction would see identical
    `now()` values regardless of whether `onupdate` fired at all.
    """
    engine = create_async_engine(url)
    try:
        resume_id = uuid.uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                ResumeRow.__table__.insert().values(id=resume_id, name="Alice")
            )
            first = (
                await connection.execute(
                    select(ResumeRow.created_at, ResumeRow.updated_at).where(
                        ResumeRow.id == resume_id
                    )
                )
            ).one()

        await asyncio.sleep(0.01)

        async with engine.begin() as connection:
            await connection.execute(
                update(ResumeRow).where(ResumeRow.id == resume_id).values(name="Alice Updated")
            )
            second = (
                await connection.execute(
                    select(ResumeRow.created_at, ResumeRow.updated_at).where(
                        ResumeRow.id == resume_id
                    )
                )
            ).one()
        return first, second
    finally:
        await engine.dispose()


def test_updated_at_is_bumped_by_an_update_issued_through_sqlalchemy(
    migrated_database: str,
) -> None:
    """Confirms `onupdate=func.now()` actually fires -- not just that it's configured.

    This is specifically an UPDATE issued *through SQLAlchemy* (Core, via
    `ResumeRow.__table__`) -- the `onupdate` mechanism is client-side, not
    a database trigger, so it would not fire for a raw SQL UPDATE issued
    outside SQLAlchemy. That is the deliberate, documented tradeoff (see
    `ResumeRow.updated_at`'s comment), not a gap this test needs to cover.
    """
    first, second = asyncio.run(_insert_and_bump(migrated_database))

    assert second.updated_at > first.updated_at
    assert second.created_at == first.created_at


def test_downgrade_then_upgrade_leaves_no_diff(migrated_database: str) -> None:
    """`alembic check` after a downgrade+upgrade cycle stays clean.

    Exercises the migration's `downgrade()` explicitly, in addition to the
    implicit downgrade every other test's fixture teardown already relies
    on -- and confirms re-applying `upgrade()` afterward reproduces
    exactly the schema `Base.metadata` describes, with no leftover drift.
    """
    downgrade_test_database()
    upgrade_test_database()

    # No AssertionError/CommandError means autogenerate found no diff
    # between the live (just re-migrated) database and Base.metadata.
    check_test_database()
