"""Unit tests for `record_interview_preparation` (Interview Preparation's persistence boundary).

Mirrors `test_job_preparation_persistence.py`'s own direct-against-the-store
style for the other `record_*` orchestration functions.
"""

import pytest

from app.orchestration.job_preparation_persistence import (
    record_interview_preparation,
    start_job_preparation,
)
from app.persistence.errors import JobPreparationCompletedError, JobPreparationNotFoundError
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.models import JobPreparationStatus

_ANALYSIS = {"overall_assessment": {"overall_score": 70}}
_GUIDE = {
    "system_design_questions": [],
    "coding_questions": [],
    "behavioral_questions": [],
    "generated_at": "2026-08-12T00:00:00Z",
}


async def test_record_interview_preparation_persists_the_guide() -> None:
    store = InMemoryPersistenceStore()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )

    updated = await record_interview_preparation(store, job_preparation.id, _GUIDE)

    assert updated.interview_preparation == _GUIDE
    reloaded = await store.get_job_preparation(job_preparation.id)
    assert reloaded.interview_preparation == _GUIDE


async def test_record_interview_preparation_raises_for_an_unknown_job_preparation() -> None:
    from uuid import uuid4

    store = InMemoryPersistenceStore()

    with pytest.raises(JobPreparationNotFoundError):
        await record_interview_preparation(store, uuid4(), _GUIDE)


async def test_record_interview_preparation_raises_for_a_completed_job_preparation() -> None:
    store = InMemoryPersistenceStore()
    job_preparation = await start_job_preparation(
        store, resume_text="Resume text", job_description="JD text", analysis_result=_ANALYSIS
    )
    resume_version = await store.get_resume_version(job_preparation.source_resume_version_id)
    applied = await store.apply_resume_version(
        job_preparation.id,
        content=resume_version.content,
        selected_suggestion_ids=[],
        edited_texts={},
    )
    await store.save_job_preparation(
        applied.model_copy(update={"status": JobPreparationStatus.COMPLETED})
    )

    with pytest.raises(JobPreparationCompletedError):
        await record_interview_preparation(store, job_preparation.id, _GUIDE)
