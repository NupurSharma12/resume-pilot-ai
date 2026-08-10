"""PostgreSQL-backed `PersistenceStore` implementation.

`PersistenceStore` (`app.persistence.store`) is an `async def` Protocol,
and this store is genuinely async all the way through: each public method
directly awaits SQLAlchemy 2.x async calls against `asyncpg` -- no
`asyncio.run()`, no synchronous wrapper hiding an async body underneath.
A caller (a FastAPI async endpoint, once Phase 3 wires one up; today,
this store's own tests) simply `await`s these methods directly, on
whatever event loop is already running.

ENGINE / SESSION LIFECYCLE
--------------------------
One `AsyncEngine` (ordinary pooling -- no `NullPool`, no per-call engine
construction) is created once, in `__init__`, and reused for every method
call for this store instance's lifetime. `create_async_engine` itself
performs no I/O -- it only configures a connection factory -- so
constructing this class still never connects to the database (see
`build_persistence_store`'s requirement that selecting `postgres` must
not itself require one). The engine is an *instance* attribute, not a
module-level global: its lifetime is owned by whoever constructs this
store (today, `build_persistence_store`, called once per `create_app`
and attached to `app.state.persistence_store` -- the same
process-lifetime-singleton treatment `ConversationSessionStore`/
`TailoringPlanStore` already get). `dispose()` releases the pool's
connections; nothing calls it yet (wiring it into `app.py`'s `lifespan`
shutdown is a Phase 3 concern, not required to construct or use this
store correctly), but the method exists now so that lifecycle is
something the application *can* own, deliberately, when it needs to.

Each method still opens its own short-lived `AsyncSession` from the
shared `async_sessionmaker` (`self._session_factory()`) -- sessions are
per-operation, never held across calls or handed out to callers; only
the underlying engine/pool is now long-lived.

DOMAIN <-> ORM MAPPING
----------------------
Every method converts `app.persistence.db.tables` ORM rows to
`app.persistence.models` Pydantic domain objects (via the `_*_from_row`
helpers below) before its session closes -- callers of this class only
ever see `Resume`/`ResumeVersion`/`JobPreparation`, never a `ResumeRow`/
`ResumeVersionRow`/`JobPreparationRow` or any other SQLAlchemy object.

TRANSACTIONS
------------
Every mutation runs inside exactly one `session.begin()` block: on success
it commits when that block exits; on any exception (including a translated
`PersistenceError`) it rolls back, so a rejected write is never partially
applied. Reads use a session with no explicit `begin()` -- SQLAlchemy still
wraps a bare `execute()` in an implicit transaction, but there's nothing to
commit for a read, so this simply lets it close.

ERROR TRANSLATION
------------------
Only the specific `IntegrityError`s this schema's own constraints can
produce are caught and translated, by constraint name (see
`_constraint_name`) -- never a blanket `except Exception`. An
`IntegrityError` whose constraint doesn't match a known, expected case (or
any other database failure -- a dropped connection, a timeout, a syntax
error) propagates as-is, so a genuine bug or outage is never disguised as
an ordinary, expected `PersistenceError`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.persistence.db.tables import JobPreparationRow, ResumeRow, ResumeVersionRow
from app.persistence.errors import (
    ConcurrentResumeVersionConflictError,
    InvalidJobPreparationStatusError,
    InvalidResumeVersionSourceError,
    JobPreparationCompletedError,
    JobPreparationNotFoundError,
    ResumeNotFoundError,
    ResumeVersionNotFoundError,
)
from app.persistence.models import (
    JobPreparation,
    JobPreparationStatus,
    Resume,
    ResumeVersion,
    ResumeVersionSource,
)

# Constraint names as actually created by the frozen migration (see
# db/base.py's NAMING_CONVENTION and db/tables.py's __table_args__) --
# matched against IntegrityError.orig.constraint_name to translate an
# expected constraint violation into its PersistenceError equivalent
# without ever pattern-matching on a raw error message string.
_UNIQUE_RESUME_VERSION = "uq_resume_versions_resume_id_version_number"
_FK_JOB_PREPARATIONS_APPLIED_VERSION = (
    "fk_job_preparations_applied_resume_version_id_resume_versions"
)


def _resume_from_row(row: ResumeRow) -> Resume:
    return Resume(id=row.id, name=row.name, created_at=row.created_at, updated_at=row.updated_at)


def _resume_version_from_row(row: ResumeVersionRow) -> ResumeVersion:
    return ResumeVersion(
        id=row.id,
        resume_id=row.resume_id,
        version_number=row.version_number,
        content=row.content,
        source=ResumeVersionSource(row.source),
        created_at=row.created_at,
    )


def _job_preparation_from_row(row: JobPreparationRow) -> JobPreparation:
    return JobPreparation(
        id=row.id,
        source_resume_version_id=row.source_resume_version_id,
        applied_resume_version_id=row.applied_resume_version_id,
        job_title=row.job_title,
        company=row.company,
        job_description=row.job_description,
        analysis_result=row.analysis_result,
        career_conversation=row.career_conversation,
        tailoring_plan=row.tailoring_plan,
        post_apply_analysis=row.post_apply_analysis,
        interview_preparation=row.interview_preparation,
        status=JobPreparationStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    """Best-effort extraction of the failed constraint's name from a wrapped asyncpg error.

    Two layers of wrapping to see through: SQLAlchemy's own `IntegrityError`
    (the public exception type this module catches) wraps `.orig`, but for
    the asyncpg dialect `.orig` is itself SQLAlchemy's DBAPI-compatibility
    shim (`AsyncAdapt_asyncpg_dbapi.IntegrityError`) -- a thin re-raise that
    does *not* carry `constraint_name`. The real `asyncpg.exceptions.
    PostgresError`, which does (populated by PostgreSQL itself in the
    wire-protocol error response, not parsed out of a message string), is
    chained onto that shim as `__cause__` (SQLAlchemy raises it `from` the
    original asyncpg error) -- verified directly against a real unique
    violation, not assumed from documentation alone.
    """
    cause = exc.orig.__cause__ if exc.orig is not None else None
    return getattr(cause, "constraint_name", None)


class PostgresPersistenceStore:
    """PostgreSQL-backed `PersistenceStore`. See module docstring for its design."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def dispose(self) -> None:
        """Release this store's connection pool.

        Not part of `PersistenceStore` -- see module docstring.
        """
        await self._engine.dispose()

    # ---- Resumes ---------------------------------------------------

    async def create_resume(self, name: str) -> Resume:
        async with self._session_factory() as session, session.begin():
            row = ResumeRow(id=uuid.uuid4(), name=name)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return _resume_from_row(row)

    async def get_resume(self, resume_id: uuid.UUID) -> Resume | None:
        async with self._session_factory() as session:
            row = await session.get(ResumeRow, resume_id)
            return _resume_from_row(row) if row is not None else None

    # ---- Resume versions ---------------------------------------------

    async def create_resume_version(
        self, resume_id: uuid.UUID, content: str, source: ResumeVersionSource
    ) -> ResumeVersion:
        async with self._session_factory() as session, session.begin():
            resume = await session.get(ResumeRow, resume_id)
            if resume is None:
                raise ResumeNotFoundError(f"No resume with id {resume_id!r}.")

            max_version_number = await session.scalar(
                select(func.max(ResumeVersionRow.version_number)).where(
                    ResumeVersionRow.resume_id == resume_id
                )
            )
            next_version_number = (max_version_number or 0) + 1
            is_first_version = next_version_number == 1
            if (source == ResumeVersionSource.ORIGINAL_UPLOAD) != is_first_version:
                raise InvalidResumeVersionSourceError(
                    f"source={source!r} is invalid for version_number={next_version_number}: "
                    "'original_upload' must be the first version, and the first version must "
                    "be 'original_upload'."
                )

            row = ResumeVersionRow(
                id=uuid.uuid4(),
                resume_id=resume_id,
                version_number=next_version_number,
                content=content,
                source=source.value,
            )
            session.add(row)
            try:
                await session.flush()
            except IntegrityError as exc:
                if _constraint_name(exc) == _UNIQUE_RESUME_VERSION:
                    raise ConcurrentResumeVersionConflictError(
                        f"Lost a race to create version_number={next_version_number} for "
                        f"resume {resume_id!r} -- another version was committed first. "
                        "Retry create_resume_version()."
                    ) from exc
                raise
            await session.refresh(row)
            return _resume_version_from_row(row)

    async def get_resume_version(self, version_id: uuid.UUID) -> ResumeVersion | None:
        async with self._session_factory() as session:
            row = await session.get(ResumeVersionRow, version_id)
            return _resume_version_from_row(row) if row is not None else None

    async def list_resume_versions(self, resume_id: uuid.UUID) -> list[ResumeVersion]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(ResumeVersionRow)
                    .where(ResumeVersionRow.resume_id == resume_id)
                    .order_by(ResumeVersionRow.version_number.asc())
                )
            ).all()
            return [_resume_version_from_row(row) for row in rows]

    # ---- Job preparations ----------------------------------------------

    async def create_job_preparation(
        self,
        source_resume_version_id: uuid.UUID,
        job_title: str,
        job_description: str,
        company: str | None = None,
    ) -> JobPreparation:
        async with self._session_factory() as session, session.begin():
            version = await session.get(ResumeVersionRow, source_resume_version_id)
            if version is None:
                raise ResumeVersionNotFoundError(
                    f"No resume version with id {source_resume_version_id!r}."
                )

            row = JobPreparationRow(
                id=uuid.uuid4(),
                source_resume_version_id=source_resume_version_id,
                applied_resume_version_id=None,
                job_title=job_title,
                company=company,
                job_description=job_description,
                analysis_result=None,
                career_conversation=None,
                tailoring_plan=None,
                post_apply_analysis=None,
                interview_preparation=None,
                status=JobPreparationStatus.DRAFT.value,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return _job_preparation_from_row(row)

    async def get_job_preparation(self, job_preparation_id: uuid.UUID) -> JobPreparation | None:
        async with self._session_factory() as session:
            row = await session.get(JobPreparationRow, job_preparation_id)
            return _job_preparation_from_row(row) if row is not None else None

    async def save_job_preparation(self, job_preparation: JobPreparation) -> JobPreparation:
        async with self._session_factory() as session, session.begin():
            # SELECT ... FOR UPDATE: locks this row for the rest of the
            # transaction so two concurrent save_job_preparation() calls
            # against the *same* preparation can't both pass the
            # "not already completed" check below before either commits --
            # a real hazard for a multi-connection database that
            # InMemoryPersistenceStore's single-process, GIL-serialized
            # dict mutation never has. Not "sophisticated" locking: one
            # row, one short-lived lock, released automatically when this
            # transaction ends.
            current = (
                await session.execute(
                    select(JobPreparationRow)
                    .where(JobPreparationRow.id == job_preparation.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()

            if current is None:
                raise JobPreparationNotFoundError(
                    f"No job preparation with id {job_preparation.id!r}. "
                    "save_job_preparation() cannot create a new one -- use "
                    "create_job_preparation()."
                )
            if current.status == JobPreparationStatus.COMPLETED.value:
                raise JobPreparationCompletedError(
                    f"Job preparation {job_preparation.id!r} is already completed and is "
                    "read-only history -- it cannot be saved again."
                )
            if (
                job_preparation.status == JobPreparationStatus.COMPLETED
                and job_preparation.applied_resume_version_id is None
            ):
                raise InvalidJobPreparationStatusError(
                    f"Job preparation {job_preparation.id!r} cannot be saved as 'completed' "
                    "without an applied_resume_version_id."
                )
            if job_preparation.applied_resume_version_id is not None:
                applied_version = await session.get(
                    ResumeVersionRow, job_preparation.applied_resume_version_id
                )
                if applied_version is None:
                    raise ResumeVersionNotFoundError(
                        f"No resume version with id {job_preparation.applied_resume_version_id!r}."
                    )

            # Whole-row replace (except `id`, and `updated_at` which
            # `onupdate=func.now()` recomputes automatically on this
            # UPDATE) -- mirrors InMemoryPersistenceStore.save_job_preparation's
            # `self._job_preparations[saved.id] = saved` exactly: the
            # caller-supplied object is trusted as the complete new state.
            current.source_resume_version_id = job_preparation.source_resume_version_id
            current.applied_resume_version_id = job_preparation.applied_resume_version_id
            current.job_title = job_preparation.job_title
            current.company = job_preparation.company
            current.job_description = job_preparation.job_description
            current.analysis_result = job_preparation.analysis_result
            current.career_conversation = job_preparation.career_conversation
            current.tailoring_plan = job_preparation.tailoring_plan
            current.post_apply_analysis = job_preparation.post_apply_analysis
            current.interview_preparation = job_preparation.interview_preparation
            current.status = job_preparation.status.value
            current.created_at = job_preparation.created_at

            try:
                await session.flush()
            except IntegrityError as exc:
                if _constraint_name(exc) == _FK_JOB_PREPARATIONS_APPLIED_VERSION:
                    # Defensive only: the pre-check above already covers
                    # every reachable path in today's application (nothing
                    # deletes a ResumeVersion), so this can't currently
                    # fire outside of a hand-crafted test -- kept so a
                    # future code path that *can* race here still gets a
                    # typed PersistenceError instead of a raw IntegrityError.
                    raise ResumeVersionNotFoundError(
                        f"No resume version with id {job_preparation.applied_resume_version_id!r}."
                    ) from exc
                raise
            await session.refresh(current)
            return _job_preparation_from_row(current)
