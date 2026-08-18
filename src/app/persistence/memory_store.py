"""In-memory `PersistenceStore` implementation: the default, zero-configuration backend.

Backs every entity with a plain `dict` keyed by id, exactly the pattern
`ConversationSessionStore`/`TailoringPlanStore` already use for their own
process-lifetime state (see their module docstrings) — this class is the
durable-product-history counterpart to those two, not a replacement for
them. Same explicit scope boundary: no persistence across a process
restart, no cross-process sharing. That is acceptable for `memory`, the
default backend meant for a developer to clone and run with zero database
configuration — `PostgresPersistenceStore` (`postgres_store.py`) is what
makes this durable across restarts, for a process configured to use it.

Every integrity rule the agreed PostgreSQL schema expresses as a
constraint (foreign keys, `UNIQUE(resume_id, version_number)`, the two
`CHECK`s) is enforced here in Python, so behavior is consistent regardless
of which `PersistenceStore` implementation is configured — a caller
should never be able to construct invalid state against `memory` that
`postgres` would have rejected, or vice versa.

Every method is `async def`, matching `PersistenceStore` (see its module
docstring for why) even though nothing here actually awaits anything: a
dict lookup has no I/O to yield on. This is not a performance-motivated
choice, only a contract one -- `InMemoryPersistenceStore` and
`PostgresPersistenceStore` must be interchangeable behind one `await`-able
interface, and there is deliberately no artificial `asyncio.sleep`,
executor hop, or lock added here to "simulate" async work -- that would
misrepresent what this backend actually does.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.persistence.errors import (
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


class InMemoryPersistenceStore:
    """Process-lifetime, in-memory `PersistenceStore`. See module docstring for scope."""

    def __init__(self) -> None:
        self._resumes: dict[UUID, Resume] = {}
        self._resume_versions: dict[UUID, ResumeVersion] = {}
        self._job_preparations: dict[UUID, JobPreparation] = {}

    async def create_resume(self, name: str) -> Resume:
        now = datetime.now(UTC)
        resume = Resume(id=uuid4(), name=name, created_at=now, updated_at=now)
        self._resumes[resume.id] = resume
        return resume

    async def get_resume(self, resume_id: UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    async def create_resume_version(
        self, resume_id: UUID, content: str, source: ResumeVersionSource
    ) -> ResumeVersion:
        if resume_id not in self._resumes:
            raise ResumeNotFoundError(f"No resume with id {resume_id!r}.")

        existing = await self.list_resume_versions(resume_id)
        next_version_number = existing[-1].version_number + 1 if existing else 1
        is_first_version = next_version_number == 1
        if (source == ResumeVersionSource.ORIGINAL_UPLOAD) != is_first_version:
            raise InvalidResumeVersionSourceError(
                f"source={source!r} is invalid for version_number={next_version_number}: "
                "'original_upload' must be the first version, and the first version must "
                "be 'original_upload'."
            )

        version = ResumeVersion(
            id=uuid4(),
            resume_id=resume_id,
            version_number=next_version_number,
            content=content,
            source=source,
            created_at=datetime.now(UTC),
        )
        self._resume_versions[version.id] = version
        return version

    async def get_resume_version(self, version_id: UUID) -> ResumeVersion | None:
        return self._resume_versions.get(version_id)

    async def list_resume_versions(self, resume_id: UUID) -> list[ResumeVersion]:
        versions = [v for v in self._resume_versions.values() if v.resume_id == resume_id]
        return sorted(versions, key=lambda v: v.version_number)

    async def create_job_preparation(
        self,
        source_resume_version_id: UUID,
        job_title: str,
        job_description: str,
        company: str | None = None,
        include_in_history: bool = True,
    ) -> JobPreparation:
        if source_resume_version_id not in self._resume_versions:
            raise ResumeVersionNotFoundError(
                f"No resume version with id {source_resume_version_id!r}."
            )

        now = datetime.now(UTC)
        job_preparation = JobPreparation(
            id=uuid4(),
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
            initial_analysis_completed_at=None,
            career_conversation_completed_at=None,
            tailoring_plan_completed_at=None,
            applied_at=None,
            post_apply_analysis_completed_at=None,
            status=JobPreparationStatus.DRAFT,
            created_at=now,
            updated_at=now,
            include_in_history=include_in_history,
            deleted_at=None,
        )
        self._job_preparations[job_preparation.id] = job_preparation
        return job_preparation

    async def get_job_preparation(self, job_preparation_id: UUID) -> JobPreparation | None:
        return self._job_preparations.get(job_preparation_id)

    async def save_job_preparation(self, job_preparation: JobPreparation) -> JobPreparation:
        current = self._job_preparations.get(job_preparation.id)
        if current is None:
            raise JobPreparationNotFoundError(
                f"No job preparation with id {job_preparation.id!r}. "
                "save_job_preparation() cannot create a new one -- use create_job_preparation()."
            )
        if current.status == JobPreparationStatus.COMPLETED:
            raise JobPreparationCompletedError(
                f"Job preparation {job_preparation.id!r} is already completed and is read-only "
                "history -- it cannot be saved again."
            )
        if (
            job_preparation.status == JobPreparationStatus.COMPLETED
            and job_preparation.applied_resume_version_id is None
        ):
            raise InvalidJobPreparationStatusError(
                f"Job preparation {job_preparation.id!r} cannot be saved as 'completed' without "
                "an applied_resume_version_id."
            )
        if (
            job_preparation.applied_resume_version_id is not None
            and job_preparation.applied_resume_version_id not in self._resume_versions
        ):
            raise ResumeVersionNotFoundError(
                f"No resume version with id {job_preparation.applied_resume_version_id!r}."
            )

        saved = job_preparation.model_copy(update={"updated_at": datetime.now(UTC)})
        self._job_preparations[saved.id] = saved
        return saved

    async def apply_resume_version(
        self,
        job_preparation_id: UUID,
        *,
        content: str,
        selected_suggestion_ids: list[str],
        edited_texts: dict[str, str],
    ) -> JobPreparation:
        current = self._job_preparations.get(job_preparation_id)
        if current is None:
            raise JobPreparationNotFoundError(f"No job preparation with id {job_preparation_id!r}.")
        if current.status == JobPreparationStatus.COMPLETED:
            raise JobPreparationCompletedError(
                f"Job preparation {job_preparation_id!r} is already completed and is read-only "
                "history -- it cannot be saved again."
            )

        # Both mutations below happen with no `await` between them -- a
        # single-threaded, GIL-serialized sequence is already exactly as
        # atomic (from any other coroutine's point of view) as
        # PostgresPersistenceStore's explicit `session.begin()` block. No
        # lock or transaction object is needed to get that guarantee here.
        source_resume_id = self._resume_versions[current.source_resume_version_id].resume_id
        applied_version = await self.create_resume_version(
            source_resume_id, content=content, source=ResumeVersionSource.APPLIED
        )

        now = datetime.now(UTC)
        generated_plan = (current.tailoring_plan or {}).get("generated_plan")
        updated = current.model_copy(
            update={
                "applied_resume_version_id": applied_version.id,
                "applied_at": now,
                "tailoring_plan": {
                    "generated_plan": generated_plan,
                    "selection": {
                        "selected_suggestion_ids": selected_suggestion_ids,
                        "edited_texts": edited_texts,
                    },
                },
                "updated_at": now,
            }
        )
        self._job_preparations[updated.id] = updated
        return updated

    def _resume_name_for(self, job_preparation: JobPreparation) -> str:
        version = self._resume_versions[job_preparation.source_resume_version_id]
        return self._resumes[version.resume_id].name

    def _filtered_job_preparations(
        self,
        *,
        resume_id: UUID | None,
        company: str | None,
        job_title: str | None,
        updated_after: datetime | None,
        search: str | None,
    ) -> list[JobPreparation]:
        """Shared filtering logic for `list_job_preparations`/`count_job_preparations` --
        unsorted, unsliced; each caller applies its own ordering/pagination or just takes `len()`.
        """
        results = [
            jp
            for jp in self._job_preparations.values()
            if jp.include_in_history and jp.deleted_at is None
        ]
        if resume_id is not None:
            results = [
                jp
                for jp in results
                if self._resume_versions[jp.source_resume_version_id].resume_id == resume_id
            ]
        if company is not None:
            results = [jp for jp in results if jp.company == company]
        if job_title is not None:
            results = [jp for jp in results if jp.job_title == job_title]
        if updated_after is not None:
            results = [jp for jp in results if jp.updated_at > updated_after]
        if search is not None:
            term = search.lower()
            results = [
                jp
                for jp in results
                if term in jp.job_title.lower()
                or (jp.company is not None and term in jp.company.lower())
                or term in self._resume_name_for(jp).lower()
            ]
        return results

    async def list_job_preparations(
        self,
        *,
        resume_id: UUID | None = None,
        company: str | None = None,
        job_title: str | None = None,
        updated_after: datetime | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobPreparation]:
        results = self._filtered_job_preparations(
            resume_id=resume_id,
            company=company,
            job_title=job_title,
            updated_after=updated_after,
            search=search,
        )
        results.sort(key=lambda jp: jp.updated_at, reverse=True)
        return results[offset : offset + limit]

    async def count_job_preparations(
        self,
        *,
        resume_id: UUID | None = None,
        company: str | None = None,
        job_title: str | None = None,
        updated_after: datetime | None = None,
        search: str | None = None,
    ) -> int:
        return len(
            self._filtered_job_preparations(
                resume_id=resume_id,
                company=company,
                job_title=job_title,
                updated_after=updated_after,
                search=search,
            )
        )

    async def soft_delete_job_preparation(self, job_preparation_id: UUID) -> JobPreparation:
        current = self._job_preparations.get(job_preparation_id)
        if current is None:
            raise JobPreparationNotFoundError(f"No job preparation with id {job_preparation_id!r}.")
        if current.deleted_at is not None:
            return current

        now = datetime.now(UTC)
        updated = current.model_copy(update={"deleted_at": now, "updated_at": now})
        self._job_preparations[updated.id] = updated
        return updated
