"""Request/response schemas for `POST /v1/analyze`.

These models define the HTTP contract for the analyze-resume endpoint.
They are deliberately kept separate from `app.models.resume_analysis`
(the domain model): the API schema describes what a client sends and
receives over HTTP, while the domain model describes what the application
computes internally. Keeping them distinct means the HTTP contract can
evolve (e.g. adding pagination, a response envelope, or renamed fields for
API-versioning reasons) without forcing a change to the domain model, and
vice versa.
"""

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeResumeRequest(BaseModel):
    """Request body for `POST /v1/analyze`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume: str = Field(description="Raw resume text to analyze.")
    job_description: str = Field(
        description="Raw job description text to analyze the resume against."
    )


class AnalyzeResumeResponse(BaseModel):
    """Response body for `POST /v1/analyze`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int = Field(
        description="Overall fit score for the resume against the job description (0-100)."
    )
    missing_skills: list[str] = Field(
        description="Skills the job description calls for that the resume does not demonstrate."
    )
    strengths: list[str] = Field(
        description="Aspects of the resume that align well with the job description."
    )
    weaknesses: list[str] = Field(
        description="Aspects of the resume that fall short relative to the job description."
    )
