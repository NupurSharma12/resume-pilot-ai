"""Request/response schemas for the History endpoints (`GET /v1/job-preparations*`).

Two shapes, matching the two things a History screen actually needs:
`JobPreparationSummaryResponse` for the list (deliberately lightweight --
no JSONB payloads), and `JobPreparationDetailResponse` for opening one
preparation (the full persisted state). Both share
`CheckpointStatusResponse`, a direct pass-through of the five checkpoint
timestamps already on `app.persistence.models.JobPreparation` -- a
checkpoint is complete exactly when its timestamp is non-null, never
inferred from payload shape (see that module's docstring).

The detail response's `analysis_result`/`career_conversation`/
`tailoring_plan`/`post_apply_analysis` fields are typed as plain
`dict | None` -- the exact JSONB payloads already stored, passed through
unchanged rather than re-parsed into `AnalyzeResumeResponse`/
`ConversationSessionResponse`/etc. Each of those already-existing
domain/API models remains the source of truth for what a caller *writes*
into these columns (see `app.orchestration.job_preparation_persistence`);
duplicating them here field-by-field just to read the same data back
would be exactly the kind of unnecessary domain-model duplication this
feature's design explicitly avoids.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckpointStatusResponse(BaseModel):
    """The five independent checkpoint-completion timestamps for one `JobPreparation`.

    Mirrors `app.persistence.models.JobPreparation`'s five `*_completed_at`
    fields exactly, field for field -- a checkpoint is complete iff its
    field here is non-null. Deliberately five, not four: "Tailored
    Resume" (`applied_at`) and "Re-analysis" (`post_apply_analysis_completed_at`)
    are tracked separately since Apply and Reanalyze are independent
    requests that can succeed or fail independently of each other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_analysis_completed_at: datetime | None = Field(
        description="When Initial Analysis completed, or null if it hasn't yet."
    )
    career_conversation_completed_at: datetime | None = Field(
        description="When the Career Conversation completed, or null if it hasn't yet."
    )
    tailoring_plan_completed_at: datetime | None = Field(
        description="When the Tailoring Plan was generated, or null if it hasn't yet."
    )
    applied_at: datetime | None = Field(
        description="When the Tailored Resume was created (Apply), or null if it hasn't yet."
    )
    post_apply_analysis_completed_at: datetime | None = Field(
        description="When Re-analysis completed, or null if it hasn't yet."
    )


class JobPreparationSummaryResponse(BaseModel):
    """One row of `GET /v1/job-preparations` -- lightweight, no JSONB payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Stable identifier for this job preparation.")
    job_title: str = Field(description="The target role's title.")
    company: str | None = Field(description="The target role's company, if known.")
    resume_name: str = Field(
        description="The candidate resume's human-readable label (see Resume.name)."
    )
    created_at: datetime = Field(description="When this preparation was created.")
    updated_at: datetime = Field(description="When this preparation was last updated.")
    checkpoints: CheckpointStatusResponse = Field(
        description="Completion timestamps for all five checkpoints."
    )


class JobPreparationListResponse(BaseModel):
    """Response body for `GET /v1/job-preparations`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[JobPreparationSummaryResponse] = Field(
        description="Matching job preparations, newest-updated first."
    )


class JobPreparationDetailResponse(BaseModel):
    """Response body for `GET /v1/job-preparations/{id}` -- the full persisted state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Stable identifier for this job preparation.")
    job_title: str = Field(description="The target role's title.")
    company: str | None = Field(description="The target role's company, if known.")
    job_description: str = Field(description="The full job description text.")
    resume_name: str = Field(
        description="The candidate resume's human-readable label (see Resume.name)."
    )
    resume_text: str = Field(
        description=(
            "The source resume version's full text (see JobPreparation."
            "source_resume_version_id) -- needed to rehydrate an active session from History, "
            "not merely to display a label."
        )
    )
    status: str = Field(description="Current lifecycle state (draft/active/completed).")
    created_at: datetime = Field(description="When this preparation was created.")
    updated_at: datetime = Field(description="When this preparation was last updated.")
    checkpoints: CheckpointStatusResponse = Field(
        description="Completion timestamps for all five checkpoints."
    )

    analysis_result: dict | None = Field(
        description="Checkpoint 1 (Initial Analysis): the persisted analysis, or null."
    )
    career_conversation: dict | None = Field(
        description="Checkpoint 2 (Career Conversation): the persisted session state, or null."
    )
    tailoring_plan: dict | None = Field(
        description=(
            "Checkpoint 3 (Tailoring Plan): {'generated_plan': ..., 'selection': ...}, or null."
        )
    )
    applied_resume_text: str | None = Field(
        description="Checkpoint 4 (Tailored Resume): the applied resume's full text, or null."
    )
    post_apply_analysis: dict | None = Field(
        description=(
            "Checkpoint 5 (Re-analysis): {'analysis': ..., 'comparison': ..., "
            "'reanalyzed_at': ...}, or null."
        )
    )
    interview_preparation: dict | None = Field(
        description="The generated Interview Preparation guide, or null if none has been generated."
    )
