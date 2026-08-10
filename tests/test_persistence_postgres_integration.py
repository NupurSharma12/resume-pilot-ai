"""PostgreSQL-only integration tests for `PostgresPersistenceStore`.

Covers what the shared contract suite (`test_persistence_contract.py`)
deliberately can't: behavior that only exists because a real, concurrent,
constraint-enforcing database is involved -- `InMemoryPersistenceStore`
has no equivalent (a single-process dict mutation under the GIL can't
race with itself), so there is no "shared" test body to write for it.

`PostgresPersistenceStore` is genuinely `async def` all the way through
(no `asyncio.run()` anywhere in it -- see its module docstring), so every
test here is a plain `async def test_...` that `await`s the store
directly, on the one event loop pytest-asyncio's `asyncio_mode = "auto"`
already provides for the test itself.

Skipped cleanly (module-level) unless `RESUMEPILOT_TEST_DATABASE_URL` is
set, via the same opt-in mechanism as the rest of this project's
PostgreSQL-specific tests (see `tests/persistence_db_support.py`).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.persistence.db.tables import ResumeVersionRow
from app.persistence.errors import ConcurrentResumeVersionConflictError
from app.persistence.models import ResumeVersionSource
from app.persistence.postgres_store import PostgresPersistenceStore, _constraint_name
from tests.persistence_db_support import (
    TEST_DATABASE_URL,
    downgrade_test_database,
    upgrade_test_database,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "RESUMEPILOT_TEST_DATABASE_URL is not set -- skipping PostgreSQL-only "
        "PostgresPersistenceStore integration tests."
    ),
)

_UNIQUE_RESUME_VERSION = "uq_resume_versions_resume_id_version_number"


@pytest.fixture(scope="module", autouse=True)
def _postgres_schema_for_integration_tests():
    """Migrate `RESUMEPILOT_TEST_DATABASE_URL` to `head` once for this whole test module.

    Deliberately a plain (sync) fixture, not `async def`: `upgrade_test_database`/
    `downgrade_test_database` each drive their own `asyncio.run()`
    internally (Alembic's `migrations/env.py` does, for a CLI-style
    invocation -- see that module) -- calling either from *inside* an
    already-running event loop (which an `async def` fixture would be)
    raises `RuntimeError: asyncio.run() cannot be called from a running
    event loop`. A sync fixture runs during pytest's normal (non-async)
    fixture setup, outside any event loop, avoiding that entirely.
    """
    upgrade_test_database()
    yield
    downgrade_test_database()


@pytest.fixture
async def store() -> AsyncIterator[PostgresPersistenceStore]:
    # narrows for type-checkers; module-level skipif already guarantees this
    assert TEST_DATABASE_URL is not None
    postgres_store = PostgresPersistenceStore(TEST_DATABASE_URL)
    try:
        yield postgres_store
    finally:
        await postgres_store.dispose()


async def _insert_at_version_number(
    database_url: str, resume_id: uuid.UUID, version_number: int, barrier: asyncio.Barrier
) -> str:
    """Insert one `resume_versions` row, waiting at `barrier` right before the INSERT.

    Two calls sharing the same `barrier` are guaranteed to both have an
    open transaction before either one attempts its INSERT -- a
    deterministic way to force the exact race
    `UNIQUE(resume_id, version_number)` exists to guard against, rather
    than hoping two independent `asyncio.gather`-ed calls happen to
    overlap on their own. Deliberately bypasses `PostgresPersistenceStore`
    -- this needs two genuinely independent connections/transactions,
    which is exactly what `NullPool` (fresh connection, never reused)
    guarantees here.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection, connection.begin():
            await barrier.wait()
            await connection.execute(
                ResumeVersionRow.__table__.insert().values(
                    id=uuid.uuid4(),
                    resume_id=resume_id,
                    version_number=version_number,
                    content="racing insert",
                    source=ResumeVersionSource.APPLIED.value,
                )
            )
        return "ok"
    except IntegrityError as exc:
        return _constraint_name(exc) or "unknown_constraint"
    finally:
        await engine.dispose()


async def test_unique_constraint_rejects_concurrent_duplicate_version_number(
    store: PostgresPersistenceStore,
) -> None:
    """The database constraint -- not Python -- is what makes this safe under real concurrency.

    Deliberately bypasses `PostgresPersistenceStore` for the INSERTs
    themselves (two independent, hand-driven transactions racing to
    insert the identical `version_number`) to isolate exactly the claim
    this test makes: PostgreSQL's `UNIQUE(resume_id, version_number)`
    rejects the second committer, full stop, regardless of what Python
    code is or isn't running concurrently above it. See
    `test_translates_a_unique_violation_into_the_domain_error` below for
    proof that `PostgresPersistenceStore` itself correctly translates
    this exact violation.
    """
    resume = await store.create_resume(name="Alice's resume")
    await store.create_resume_version(
        resume.id, content="v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
    )

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _insert_at_version_number(TEST_DATABASE_URL, resume.id, 2, barrier),
        _insert_at_version_number(TEST_DATABASE_URL, resume.id, 2, barrier),
    )

    assert sorted(results) == ["ok", _UNIQUE_RESUME_VERSION]


async def test_translates_a_unique_violation_into_the_domain_error(
    store: PostgresPersistenceStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`create_resume_version` maps a UNIQUE-violation `IntegrityError` to the domain error.

    Deterministic, not timing-dependent: rather than relying on a real
    race actually landing inside `create_resume_version`'s own narrow
    `flush()` window (see the test above for how that's forced
    reliably instead, via an explicit barrier), `AsyncSession.flush` is
    monkeypatched to raise the exact `IntegrityError` shape a real
    unique-violation produces, isolating the one thing this test cares
    about: that `PostgresPersistenceStore.create_resume_version`'s
    `except IntegrityError` branch correctly recognizes
    `uq_resume_versions_resume_id_version_number` by name and raises
    `ConcurrentResumeVersionConflictError`, not a raw `IntegrityError`.
    """
    resume = await store.create_resume(name="Alice's resume")
    await store.create_resume_version(
        resume.id, content="v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
    )

    # Mirrors the real two-layer wrapping `_constraint_name` unwraps (see
    # its docstring): SQLAlchemy's `IntegrityError.orig` is a DBAPI shim
    # with no `constraint_name` of its own -- the real asyncpg exception
    # (which has it) is chained onto that shim as `__cause__`.
    class _FakeAsyncpgUniqueViolation(Exception):
        constraint_name = _UNIQUE_RESUME_VERSION

    class _FakeDbapiShim(Exception):
        pass

    async def _raise_unique_violation(self: AsyncSession, *args: object, **kwargs: object) -> None:
        shim = _FakeDbapiShim()
        shim.__cause__ = _FakeAsyncpgUniqueViolation()
        raise IntegrityError("INSERT INTO resume_versions ...", {}, shim)

    monkeypatch.setattr(AsyncSession, "flush", _raise_unique_violation)

    with pytest.raises(ConcurrentResumeVersionConflictError):
        await store.create_resume_version(
            resume.id, content="v2", source=ResumeVersionSource.APPLIED
        )


async def test_max_version_number_query_reflects_only_this_resume(
    store: PostgresPersistenceStore,
) -> None:
    """Sanity check on the SQL `max(version_number)` computation itself, across two resumes.

    Not a race test -- just confirms the `WHERE resume_id = ...` filter
    on the `max()` used to compute "the next version number" is actually
    scoped per-resume at the SQL level, the same property
    `test_persistence_contract.py`'s
    `test_version_numbering_is_independent_per_resume` already asserts
    through the public API; this is the same fact confirmed one layer
    lower, directly against the query.
    """
    resume_a = await store.create_resume(name="A")
    resume_b = await store.create_resume(name="B")
    await store.create_resume_version(
        resume_a.id, content="a-v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
    )
    await store.create_resume_version(
        resume_a.id, content="a-v2", source=ResumeVersionSource.APPLIED
    )

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            max_a = (
                await connection.execute(
                    select(func.max(ResumeVersionRow.version_number)).where(
                        ResumeVersionRow.resume_id == resume_a.id
                    )
                )
            ).scalar()
            max_b = (
                await connection.execute(
                    select(func.max(ResumeVersionRow.version_number)).where(
                        ResumeVersionRow.resume_id == resume_b.id
                    )
                )
            ).scalar()
    finally:
        await engine.dispose()

    assert max_a == 2
    assert max_b is None
