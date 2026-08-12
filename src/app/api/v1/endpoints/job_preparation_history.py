"""History endpoints: `GET /v1/job-preparations*`.

Read-only: `JobPreparation` is written exclusively through
`app.orchestration.job_preparation_persistence` (see the Post-Apply
Analysis Loop / Job Preparation Checkpoints work) -- these two endpoints
only ever call `PersistenceStore.list_job_preparations`/`get_job_preparation`,
translate the result to a lightweight API shape, and return it. No
checkpoint semantics live here beyond "a checkpoint is complete iff its
timestamp is non-null" -- the same rule the persistence/orchestration
layers already established.

No authentication/ownership scoping exists yet (explicitly out of scope
for this milestone -- see the History design review): every
`JobPreparation` in the configured store is visible to every caller.
"""

import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.models.job_preparation_history import (
    CheckpointStatusResponse,
    JobPreparationDetailResponse,
    JobPreparationListResponse,
    JobPreparationSummaryResponse,
)
from app.core.logging import get_logger
from app.persistence.dependencies import get_persistence_store
from app.persistence.models import JobPreparation
from app.persistence.store import PersistenceStore

logger = get_logger(__name__)

router = APIRouter()

_DEFAULT_LIST_LIMIT = 50


def _to_checkpoint_status(job_preparation: JobPreparation) -> CheckpointStatusResponse:
    return CheckpointStatusResponse(
        initial_analysis_completed_at=job_preparation.initial_analysis_completed_at,
        career_conversation_completed_at=job_preparation.career_conversation_completed_at,
        tailoring_plan_completed_at=job_preparation.tailoring_plan_completed_at,
        applied_at=job_preparation.applied_at,
        post_apply_analysis_completed_at=job_preparation.post_apply_analysis_completed_at,
    )


async def _resume_name_for(store: PersistenceStore, job_preparation: JobPreparation) -> str:
    """Resolve `job_preparation`'s candidate resume's human-readable label.

    `JobPreparation` only stores `source_resume_version_id`, not a resume
    name -- `list_job_preparations`/`get_job_preparation` return
    `JobPreparation` objects unchanged (see `PersistenceStore`'s own
    infrastructure-only scope), so this endpoint layer composes the two
    extra reads itself rather than the store pre-joining them. Both reads
    are guaranteed to succeed: nothing in this application ever deletes a
    `Resume` or `ResumeVersion`.
    """
    version = await store.get_resume_version(job_preparation.source_resume_version_id)
    resume = await store.get_resume(version.resume_id)
    return resume.name


def _to_summary_response(
    job_preparation: JobPreparation, resume_name: str
) -> JobPreparationSummaryResponse:
    return JobPreparationSummaryResponse(
        id=job_preparation.id,
        job_title=job_preparation.job_title,
        company=job_preparation.company,
        resume_name=resume_name,
        created_at=job_preparation.created_at,
        updated_at=job_preparation.updated_at,
        checkpoints=_to_checkpoint_status(job_preparation),
    )


@router.get("/job-preparations", response_model=JobPreparationListResponse)
async def list_job_preparations(
    company: str | None = None,
    job_title: str | None = None,
    updated_after: datetime | None = None,
    limit: int = _DEFAULT_LIST_LIMIT,
    store: PersistenceStore = Depends(get_persistence_store),
) -> JobPreparationListResponse:
    """List job preparations, newest-updated first.

    Filters are the same plain-column filters `PersistenceStore.list_job_preparations`
    already supports -- no full-text/JSONB search (see the History design
    review's explicit scope). `resume_id` isn't exposed as a query
    parameter here: nothing in the current frontend has a resume id to
    filter by (only a `job_preparation_id`, which already identifies one
    specific preparation, not a resume) -- it can be added later without
    an API-breaking change if a real caller needs it.
    """
    job_preparations = await store.list_job_preparations(
        company=company, job_title=job_title, updated_after=updated_after, limit=limit
    )
    resume_names = await asyncio.gather(*(_resume_name_for(store, jp) for jp in job_preparations))
    logger.info("job_preparations_listed", count=len(job_preparations))
    return JobPreparationListResponse(
        items=[
            _to_summary_response(jp, resume_name)
            for jp, resume_name in zip(job_preparations, resume_names, strict=True)
        ]
    )


@router.get("/job-preparations/{job_preparation_id}", response_model=JobPreparationDetailResponse)
async def get_job_preparation(
    job_preparation_id: UUID,
    store: PersistenceStore = Depends(get_persistence_store),
) -> JobPreparationDetailResponse:
    """Return one job preparation's full persisted state, for opening it from History.

    `404` if `job_preparation_id` is unknown. The "Tailored Resume"
    checkpoint's content (`applied_resume_text`) is resolved from
    `applied_resume_version_id` via `get_resume_version` -- the applied
    text itself isn't duplicated into `JobPreparation` anywhere; it lives
    only on its own `ResumeVersion` row, same as every other version.
    """
    job_preparation = await store.get_job_preparation(job_preparation_id)
    if job_preparation is None:
        raise HTTPException(status_code=404, detail="Job preparation not found.")

    resume_name = await _resume_name_for(store, job_preparation)
    applied_resume_text: str | None = None
    if job_preparation.applied_resume_version_id is not None:
        applied_version = await store.get_resume_version(job_preparation.applied_resume_version_id)
        applied_resume_text = applied_version.content

    logger.info("job_preparation_opened", job_preparation_id=str(job_preparation_id))
    return JobPreparationDetailResponse(
        id=job_preparation.id,
        job_title=job_preparation.job_title,
        company=job_preparation.company,
        job_description=job_preparation.job_description,
        resume_name=resume_name,
        status=job_preparation.status.value,
        created_at=job_preparation.created_at,
        updated_at=job_preparation.updated_at,
        checkpoints=_to_checkpoint_status(job_preparation),
        analysis_result=job_preparation.analysis_result,
        career_conversation=job_preparation.career_conversation,
        tailoring_plan=job_preparation.tailoring_plan,
        applied_resume_text=applied_resume_text,
        post_apply_analysis=job_preparation.post_apply_analysis,
        interview_preparation=job_preparation.interview_preparation,
    )
