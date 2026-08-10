"""In-memory `PersistenceStore` implementation: the default, zero-configuration backend.

Backs every entity with a plain `dict` keyed by id, exactly the pattern
`ConversationSessionStore`/`TailoringPlanStore` already use for their own
process-lifetime state (see their module docstrings) — this class is the
durable-product-history counterpart to those two, not a replacement for
them. Same explicit scope boundary: no persistence across a process
restart, no cross-process sharing. That is acceptable for `memory`, the
default backend meant for a developer to clone and run with zero database
configuration — a future `postgres` implementation (a later milestone)
is what makes this durable across restarts.

Every integrity rule the agreed PostgreSQL schema expresses as a
constraint (foreign keys, `UNIQUE(resume_id, version_number)`, the two
`CHECK`s) is enforced here in Python, so behavior is consistent regardless
of which `PersistenceStore` implementation is configured — a caller
should never be able to construct invalid state against `memory` that
`postgres` would have rejected, or vice versa.
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

    def create_resume(self, name: str) -> Resume:
        now = datetime.now(UTC)
        resume = Resume(id=uuid4(), name=name, created_at=now, updated_at=now)
        self._resumes[resume.id] = resume
        return resume

    def get_resume(self, resume_id: UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    def create_resume_version(
        self, resume_id: UUID, content: str, source: ResumeVersionSource
    ) -> ResumeVersion:
        if resume_id not in self._resumes:
            raise ResumeNotFoundError(f"No resume with id {resume_id!r}.")

        existing = self.list_resume_versions(resume_id)
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

    def get_resume_version(self, version_id: UUID) -> ResumeVersion | None:
        return self._resume_versions.get(version_id)

    def list_resume_versions(self, resume_id: UUID) -> list[ResumeVersion]:
        versions = [v for v in self._resume_versions.values() if v.resume_id == resume_id]
        return sorted(versions, key=lambda v: v.version_number)

    def create_job_preparation(
        self,
        source_resume_version_id: UUID,
        job_title: str,
        job_description: str,
        company: str | None = None,
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
            status=JobPreparationStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        self._job_preparations[job_preparation.id] = job_preparation
        return job_preparation

    def get_job_preparation(self, job_preparation_id: UUID) -> JobPreparation | None:
        return self._job_preparations.get(job_preparation_id)

    def save_job_preparation(self, job_preparation: JobPreparation) -> JobPreparation:
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
