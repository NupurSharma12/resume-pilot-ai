"""The persistence abstraction every backend (in-memory, PostgreSQL) must satisfy.

`PersistenceStore` is a `typing.Protocol`, the same structural-typing
choice `app.gateways.llm.gateway.LLMGateway` already makes for provider
adapters, and for the same reason: `InMemoryPersistenceStore` and
`PostgresPersistenceStore` each satisfy this contract by implementing
matching method signatures, with no shared base class and no dependency
from this module on any particular database driver or ORM.

Every method here is `async def`. This matches the only backend for
which it's actually load-bearing -- PostgreSQL access is unavoidably
asynchronous (`asyncpg`; see `app.persistence.db.engine`) -- so a
FastAPI async endpoint can `await` a `PersistenceStore` call directly,
regardless of which backend is configured, with no synchronous bridging
in between. `InMemoryPersistenceStore` has no actual I/O to await (a
dict lookup completes immediately), but implements the same `async def`
signatures anyway so both backends satisfy one interface without a
caller needing to know or care which one it's holding.

Scope is deliberately narrow: exactly the three durable entities agreed
in the Persistence phase's schema review (`Resume`, `ResumeVersion`,
`JobPreparation`), with one read/write pair per entity plus the two list/
create operations their relationships actually require. There is no
`update_resume`, no `delete_*`, no per-field setter, and no generic
repository base — none of those are used by any existing workflow today,
and this milestone does not add the endpoints that would use them (see
the module docstring in `app.persistence.memory_store` for the "why" per
method). `save_job_preparation` is the one mutation entry point for a
`JobPreparation`, mirroring `TailoringPlanStore.save`/
`ConversationSessionStore.save`'s existing save-a-whole-object convention
in this codebase, rather than a set of speculative partial-update methods.

Transient, per-request-sequence workflow state — active Career
Conversation sessions, generated-but-not-yet-applied tailoring plans —
is explicitly *not* part of this contract. `ConversationSessionStore`
and `TailoringPlanStore` continue to own that, unchanged; see their own
module docstrings for why they stay in-memory-only regardless of
`PERSISTENCE_BACKEND`. This store only ever holds what the schema review
identified as durable product history.
"""

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.persistence.models import JobPreparation, Resume, ResumeVersion, ResumeVersionSource


@runtime_checkable
class PersistenceStore(Protocol):
    """Structural interface for durable storage of resumes, their versions, and job preparations."""

    async def create_resume(self, name: str) -> Resume:
        """Create and store a new `Resume`.

        Always succeeds -- there is no uniqueness constraint on `name`.
        """
        ...

    async def get_resume(self, resume_id: UUID) -> Resume | None:
        """Return the `Resume` for `resume_id`, or `None` if it doesn't exist (or never did)."""
        ...

    async def create_resume_version(
        self, resume_id: UUID, content: str, source: ResumeVersionSource
    ) -> ResumeVersion:
        """Create the next version of `resume_id`'s content.

        `version_number` is assigned automatically (one more than the
        highest existing version for this resume, starting at 1) — callers
        never choose it, mirroring the `UNIQUE(resume_id, version_number)`
        constraint being a storage-layer invariant, not caller input.

        Raises `ResumeNotFoundError` if `resume_id` does not exist, and
        `InvalidResumeVersionSourceError` if `source` would violate
        `CHECK((source = 'original_upload') = (version_number = 1))` —
        i.e. `ORIGINAL_UPLOAD` requested for any version after the first,
        or a non-`ORIGINAL_UPLOAD` source requested for the first version.
        """
        ...

    async def get_resume_version(self, version_id: UUID) -> ResumeVersion | None:
        """Return the `ResumeVersion` for `version_id`, or `None` if it doesn't exist."""
        ...

    async def list_resume_versions(self, resume_id: UUID) -> list[ResumeVersion]:
        """Return every version of `resume_id`, ordered by `version_number` ascending.

        Returns an empty list for an unknown `resume_id`, matching this
        store's read-methods convention of "absence, not an exception" for
        pure reads (`create_resume_version` is the one place an unknown
        `resume_id` is actually an error, since creating a version implies
        the resume must already exist).
        """
        ...

    async def create_job_preparation(
        self,
        source_resume_version_id: UUID,
        job_title: str,
        job_description: str,
        company: str | None = None,
    ) -> JobPreparation:
        """Start a new `JobPreparation` from an existing resume version, in `status=draft`.

        `applied_resume_version_id` and every workflow JSONB field start
        `None`; `save_job_preparation` is how they get filled in as the
        workflow progresses. Raises `ResumeVersionNotFoundError` if
        `source_resume_version_id` does not exist.
        """
        ...

    async def get_job_preparation(self, job_preparation_id: UUID) -> JobPreparation | None:
        """Return the `JobPreparation` for `job_preparation_id`, or `None` if it doesn't exist."""
        ...

    async def save_job_preparation(self, job_preparation: JobPreparation) -> JobPreparation:
        """Persist `job_preparation` as the new current state for its `id`.

        The one mutation entry point for a `JobPreparation`: callers read
        the current state (`get_job_preparation`), build an updated copy
        (`.model_copy(update={...})`), and save it back — the same
        read-modify-write shape `TailoringPlanStore`/`ConversationSessionStore`
        already use for their own state.

        Raises `JobPreparationNotFoundError` if no preparation with this
        `id` was ever created. Raises `JobPreparationCompletedError` if the
        *currently stored* preparation is already `status=completed` —
        completed preparations are read-only history (see this module's
        docstring); the one save that transitions a preparation *into*
        `completed` is unaffected, since the previously stored record is
        not yet completed at that point. Raises
        `InvalidJobPreparationStatusError` if `job_preparation.status` is
        `completed` without an `applied_resume_version_id`. Raises
        `ResumeVersionNotFoundError` if `applied_resume_version_id` is
        set but does not reference an existing `ResumeVersion`.
        """
        ...
