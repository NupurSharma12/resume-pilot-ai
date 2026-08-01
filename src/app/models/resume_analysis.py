"""First domain model: the result shape of a resume analysis.

`ResumeAnalysisResult` describes what a resume analysis *produces*, as a
plain data contract. It contains no logic for how that result is computed
(no scoring, no skill matching, no parsing) — that will live in workflows
and agents that construct instances of this model.
"""

from pydantic import BaseModel, ConfigDict, Field


class ResumeAnalysisResult(BaseModel):
    """Structured outcome of analyzing a resume against a job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int = Field(
        ge=0,
        le=100,
        description="Overall fit score for the resume against the job description (0-100).",
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
