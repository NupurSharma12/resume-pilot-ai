"""Domain models for durable product state, mirroring the frozen PostgreSQL design.

These describe the *durable* record of a resume/job-preparation history —
`Resume`, `ResumeVersion`, `JobPreparation` — as agreed in the Persistence
phase's schema review. They are deliberately not the same models the
workflows use (`app.models.resume_analysis.ResumeAnalysisResult`,
`app.models.tailoring_suggestions.SuggestionPlan`, ...): those describe
what one workflow step produces; these describe what gets stored, field
for field, against the agreed `resumes` / `resume_versions` /
`job_preparations` tables. The workflow-JSONB columns (`analysis_result`,
`career_conversation`, `tailoring_plan`, `post_apply_analysis`,
`interview_preparation`) are typed as plain `dict | None` rather than
imported domain models — the persistence layer is an infrastructure
concern (see `app.persistence.store`) and should not be coupled to
whichever Pydantic shape a workflow happens to use today; a caller
serializes its own domain model (`.model_dump(mode="json")`) before
storing it here.

Every model is immutable (`frozen=True`), the same convention every other
domain model in this codebase uses (see e.g. `app.models.resume_analysis`)
— a "mutation" is always a new instance the store persists in place of the
old one (see `PersistenceStore.save_job_preparation`), never an in-place
field assignment.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResumeVersionSource(StrEnum):
    """How a `ResumeVersion`'s content came to exist.

    `ORIGINAL_UPLOAD` is reserved for exactly one version per resume — the
    upload that created the `Resume` itself (enforced by
    `PersistenceStore.create_resume_version`, mirroring the agreed
    `CHECK((source = 'original_upload') = (version_number = 1))`
    constraint). `APPLIED` covers every later version: the one blended
    result of an `/apply` call, which may include user-edited suggestion
    text alongside LLM-generated tailoring — the current application has
    no code path that produces a tailoring-only version followed by a
    separate user-edit-only version, so there is no separate value for that.
    """

    ORIGINAL_UPLOAD = "original_upload"
    APPLIED = "applied"


class JobPreparationStatus(StrEnum):
    """Lifecycle state of one resume + job-description preparation journey."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class Resume(BaseModel):
    """Logical resume identity. Does not identify a person — see the schema review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Stable identifier for this resume.")
    name: str = Field(description="A human-readable label for this resume.")
    created_at: datetime = Field(description="When this resume was created.")
    updated_at: datetime = Field(description="When this resume was last updated.")


class ResumeVersion(BaseModel):
    """One immutable version of a resume's content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Stable identifier for this version.")
    resume_id: UUID = Field(description="The resume this version belongs to.")
    version_number: int = Field(ge=1, description="1-indexed, unique within its resume.")
    content: str = Field(description="The version's full resume text.")
    source: ResumeVersionSource = Field(description="How this version's content came to exist.")
    created_at: datetime = Field(description="When this version was created.")


class JobPreparation(BaseModel):
    """The persisted state of one resume + job-description preparation journey.

    `analysis_result`/`career_conversation`/`tailoring_plan`/
    `post_apply_analysis`/`interview_preparation` mirror the agreed JSONB
    columns exactly, including the two composite shapes decided in the
    schema review: `tailoring_plan` holds both `generated_plan` and the
    user's `selection` (`selected_suggestion_ids`/`edited_texts`);
    `post_apply_analysis` holds both `analysis` and the deterministic
    `comparison`, plus `reanalyzed_at`. Nothing in this module validates
    those inner shapes — that is each caller's own domain model's job,
    before/after it crosses this boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(description="Stable identifier for this job preparation.")
    source_resume_version_id: UUID = Field(
        description="The resume version this preparation started from."
    )
    applied_resume_version_id: UUID | None = Field(
        description="The resume version produced by applying this preparation, once applied."
    )
    job_title: str = Field(description="The target role's title.")
    company: str | None = Field(description="The target role's company, if known.")
    job_description: str = Field(description="The full job description text.")

    analysis_result: dict | None = Field(
        description="The 'before' resume analysis, serialized, or null before analysis runs."
    )
    career_conversation: dict | None = Field(
        description="The completed career-conversation session state, serialized, or null."
    )
    tailoring_plan: dict | None = Field(
        description="{'generated_plan': ..., 'selection': {...}}, or null before generation."
    )
    post_apply_analysis: dict | None = Field(
        description="{'analysis': ..., 'comparison': ..., 'reanalyzed_at': ...}, or null."
    )
    interview_preparation: dict | None = Field(
        description="The generated Interview Preparation guide, serialized, or null."
    )

    # Five independent durable checkpoints/recovery points (see the
    # Job Preparation Checkpoints design review) -- deliberately five,
    # not four: "Tailored Resume" (applied_at) and "Re-analysis"
    # (post_apply_analysis_completed_at) are tracked separately because
    # Apply and Reanalyze are two independent requests that can succeed
    # or fail independently of each other. Each timestamp is written in
    # the exact same `save_job_preparation` call as its corresponding
    # payload/FK below -- never independently -- so a non-null timestamp
    # always means "this checkpoint's durable payload was actually
    # persisted," never merely "an attempt was made." NULL means the
    # checkpoint has not completed; a timestamp means it completed
    # successfully at that instant. No separate status enum/JSON blob is
    # used to represent this -- the timestamp itself is the signal.
    initial_analysis_completed_at: datetime | None = Field(
        description="When analysis_result was persisted, or null if it hasn't been yet."
    )
    career_conversation_completed_at: datetime | None = Field(
        description="When career_conversation was persisted, or null if it hasn't been yet."
    )
    tailoring_plan_completed_at: datetime | None = Field(
        description=(
            "When tailoring_plan.generated_plan was first persisted, or null if it hasn't "
            "been yet. Reflects generation only -- filling in tailoring_plan.selection at "
            "Apply time does not change this timestamp."
        )
    )
    applied_at: datetime | None = Field(
        description=(
            "When applied_resume_version_id was set (the 'Tailored Resume' checkpoint), or "
            "null if no changes have been applied yet."
        )
    )
    post_apply_analysis_completed_at: datetime | None = Field(
        description="When post_apply_analysis was persisted, or null if it hasn't been yet."
    )

    status: JobPreparationStatus = Field(description="Current lifecycle state.")
    created_at: datetime = Field(description="When this preparation was created.")
    updated_at: datetime = Field(description="When this preparation was last saved.")

    # History-visibility flag, independent of everything above -- see the
    # History Test Isolation & Delete design review. `False` is set only
    # by automated E2E tests (via `POST /v1/analyze`'s `X-E2E-Test`
    # header, see `analyze.py`), never by any real user flow or UI
    # control, so real preparations always default to `True`. Deliberately
    # a plain flag, not folded into `status`: it answers "should this ever
    # show up in History," an orthogonal question to the preparation's own
    # workflow lifecycle.
    include_in_history: bool = Field(
        default=True, description="Whether this preparation may appear in History at all."
    )
    # Soft-delete marker for the user-facing "Delete" action in History.
    # NULL means not deleted. Sets a timestamp rather than a bool so a
    # future permanent-purge job (explicitly out of scope today -- see
    # that design review's "Do not implement a complicated permanent-
    # delete workflow yet") has "how long has this been soft-deleted" for
    # free, without a schema change. `get_job_preparation` deliberately
    # does not filter on this (a soft-deleted preparation is still a
    # valid target for a direct-by-id lookup, e.g. Continue's rehydration
    # if it were somehow still linked to); only `list_job_preparations`
    # (History's listing) excludes it, alongside `include_in_history`.
    deleted_at: datetime | None = Field(
        default=None, description="When this preparation was soft-deleted from History, or null."
    )
