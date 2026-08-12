"""Request/response schemas for `POST /v1/analyze`.

These models define the HTTP contract for the analyze-resume endpoint.
They are deliberately kept separate from `app.models.resume_analysis`
(the domain model): the API schema describes what a client sends and
receives over HTTP, while the domain model describes what the application
computes internally. Keeping them distinct means the HTTP contract can
evolve (e.g. adding pagination, a response envelope, or renamed fields for
API-versioning reasons) without forcing a change to the domain model, and
vice versa. The response schema below mirrors `ResumeAnalysisResult`'s
current nested shape field-for-field, but each model here is its own type
so that coincidence isn't mistaken for coupling.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeResumeRequest(BaseModel):
    """Request body for `POST /v1/analyze`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume: str = Field(description="Raw resume text to analyze.")
    job_description: str = Field(
        description="Raw job description text to analyze the resume against."
    )


class HiringRecommendationResponse(BaseModel):
    """A hiring decision and the reasoning behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: str = Field(description="The recommended hiring decision.")
    reason: str = Field(description="The reasoning behind the recommended decision.")


class OverallAssessmentResponse(BaseModel):
    """A top-level summary of how well the resume fits the job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_score: int = Field(
        description="Overall fit score for the resume against the job description (0-100)."
    )
    hiring_recommendation: HiringRecommendationResponse = Field(
        description="The recommended hiring decision and its reasoning."
    )
    summary: str = Field(description="A narrative summary of the overall assessment.")


class SkillMatchResponse(BaseModel):
    """How well the resume's skills in one category match the job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(description="The skill category being assessed.")
    score: int = Field(description="Fit score for this skill category (0-100).")
    matched_skills: list[str] = Field(
        description="Skills in this category the resume demonstrates that the job calls for."
    )
    missing_skills: list[str] = Field(
        description="Skills in this category the job calls for that the resume lacks."
    )


class MatchingProjectResponse(BaseModel):
    """A project from the resume that is relevant to the job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(description="The title of the matching project.")
    relevance_score: int = Field(
        description="How relevant this project is to the job description (0-100)."
    )
    reason: str = Field(description="Why this project is considered relevant.")


class ResumeImprovementResponse(BaseModel):
    """A suggested improvement to a specific section of the resume."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The resume section this recommendation applies to.")
    recommendation: str = Field(description="The recommended change to that section.")
    priority: int = Field(description="The priority of this recommendation relative to others.")


class AnalyzeResumeResponse(BaseModel):
    """Response body for `POST /v1/analyze`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_assessment: OverallAssessmentResponse = Field(
        description="The top-level summary of the resume's fit for the job description."
    )
    skill_matches: list[SkillMatchResponse] = Field(
        description="Fit assessment broken down by skill category."
    )
    matching_projects: list[MatchingProjectResponse] = Field(
        description="Resume projects relevant to the job description."
    )
    strengths: list[str] = Field(
        description="Aspects of the resume that align well with the job description."
    )
    weaknesses: list[str] = Field(
        description="Aspects of the resume that fall short relative to the job description."
    )
    resume_improvements: list[ResumeImprovementResponse] = Field(
        description="Recommended improvements to the resume."
    )
    job_preparation_id: UUID | None = Field(
        default=None,
        description=(
            "The durable JobPreparation this analysis was recorded against (see "
            "docs/persistent-backend-workflow-state.md). Null only if this response was "
            "produced by /reanalyze (which reuses this same response shape but does not "
            "itself create a JobPreparation -- see ReanalyzeResponse). Existing clients that "
            "don't read this field are unaffected; passing it back to /career-conversation or "
            "/tailoring-suggestions lets later workflow steps attach their own durable state "
            "to the same preparation -- entirely optional."
        ),
    )
