"""Request/response schemas for `POST /v1/tailor-resume`.

Kept separate from the domain models in `app.models.tailoring_plan`/
`app.models.tailored_resume` (the HTTP contract and what the pipeline
computes internally can then evolve independently), matching
`analyze_resume.py`/`career_conversation.py`'s established split. As with
`StartConversationRequest.resume_analysis`, `TailorResumeRequest` reuses
`AnalyzeResumeResponse` and `ConversationSessionResponse` directly rather
than redefining third mirrors of the same shapes — a client tailoring a
resume is meant to replay back exactly what `POST /v1/analyze` and the
Career Conversation endpoints already gave it. `TailoringAction` is
likewise reused directly from the domain model in the response schema,
the same way `EstimatedImpact` is elsewhere: a small, fixed-membership
value enum, not an evolving object shape.

Deliberately does NOT expose the Evidence Store: it's this pipeline's
internal "facts database" (Stage 1's output, consumed by Stages 2 and 3),
not part of the public contract — a caller sees the plan that resulted
from it, the tailored resume, and the validation report, not the raw
catalog itself.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.api.v1.models.career_conversation import ConversationSessionResponse
from app.models.tailoring_plan import TailoringAction


class TailorResumeRequest(BaseModel):
    """Request body for `POST /v1/tailor-resume`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume: str = Field(description="Raw resume text to tailor.")
    job_description: str = Field(description="Raw job description text to tailor the resume for.")
    resume_analysis: AnalyzeResumeResponse = Field(
        description="The prior resume analysis result, exactly as returned by POST /v1/analyze."
    )
    career_conversation: ConversationSessionResponse = Field(
        description=(
            "The Career Conversation session's current state, exactly as returned by the "
            "Career Conversation endpoints. Its history (which may be empty, if the "
            "conversation hasn't been used or hasn't produced any completed turns yet) "
            "becomes additional evidence this tailoring run can cite."
        )
    )


class PlannedChangeResponse(BaseModel):
    """One proposed change to one resume section, and the evidence that justifies it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The resume section this change applies to.")
    action: TailoringAction = Field(description="The kind of change proposed for this section.")
    reason: str = Field(description="Why this change would improve fit for the job description.")
    evidence_ids: list[str] = Field(description="Evidence Store ids that justify this change.")


class TailoringPlanResponse(BaseModel):
    """The full set of proposed changes for one tailoring request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: list[PlannedChangeResponse] = Field(
        description="Every proposed change, in the order they should be considered."
    )


class TailoredBulletResponse(BaseModel):
    """One rewritten, validated resume bullet, and the evidence it's based on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(description="The rewritten bullet text.")
    supporting_evidence_ids: list[str] = Field(
        description="Evidence Store ids this bullet's content is based on."
    )


class TailoredSectionResponse(BaseModel):
    """One resume section, rewritten to a list of validated bullets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    heading: str = Field(description="The section heading, e.g. 'Summary', 'Experience'.")
    bullets: list[TailoredBulletResponse] = Field(
        description="The section's rewritten, validated bullets, in order."
    )


class TailoredResumeResponse(BaseModel):
    """The final, validated tailored resume — only sections/bullets that passed Validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sections: list[TailoredSectionResponse] = Field(
        description="The validated, evidence-backed tailored resume, by section."
    )


class RejectedBulletResponse(BaseModel):
    """One bullet Validation rejected, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The section heading the rejected bullet was under.")
    text: str = Field(description="The rejected bullet's text, exactly as proposed.")
    reason: str = Field(description="Why Validation rejected this bullet.")


class ValidationReportResponse(BaseModel):
    """The full record of Validation's pass over every proposed bullet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_bullets: int = Field(description="Total bullets the Rewrite Engine proposed.")
    accepted_count: int = Field(description="Bullets that passed validation and were kept.")
    rejected_count: int = Field(description="Bullets that failed validation and were dropped.")
    rejected_bullets: list[RejectedBulletResponse] = Field(
        description="Every rejected bullet and the reason it was rejected."
    )
    passed: bool = Field(
        description="True iff every proposed bullet was accepted (rejected_count == 0)."
    )


class TailorResumeResponse(BaseModel):
    """Response body for `POST /v1/tailor-resume`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tailored_resume: TailoredResumeResponse = Field(
        description="The final, validated, evidence-backed tailored resume."
    )
    tailoring_plan: TailoringPlanResponse = Field(
        description="The plan the tailored resume was produced from."
    )
    validation_report: ValidationReportResponse = Field(
        description="What was accepted and what was rejected, and why."
    )
