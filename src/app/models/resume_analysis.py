"""Domain model: the result shape of a resume analysis.

`ResumeAnalysisResult` and its nested models describe what a resume
analysis *produces*, as a set of plain, nested data contracts. They contain
no logic for how that result is computed (no scoring, no skill matching,
no parsing) — that will live in the parser and any agents that construct
instances of these models.
"""

from pydantic import BaseModel, ConfigDict, Field


class HiringRecommendation(BaseModel):
    """A hiring decision and the reasoning behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: str = Field(description="The recommended hiring decision.")
    reason: str = Field(description="The reasoning behind the recommended decision.")


class OverallAssessment(BaseModel):
    """A top-level summary of how well a resume fits a job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_score: int = Field(
        ge=0,
        le=100,
        description="Overall fit score for the resume against the job description (0-100).",
    )
    hiring_recommendation: HiringRecommendation = Field(
        description="The recommended hiring decision and its reasoning."
    )
    summary: str = Field(description="A narrative summary of the overall assessment.")


class SkillMatch(BaseModel):
    """How well the resume's skills in one category match the job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(description="The skill category being assessed.")
    score: int = Field(ge=0, le=100, description="Fit score for this skill category (0-100).")
    matched_skills: list[str] = Field(
        description="Skills in this category the resume demonstrates that the job calls for."
    )
    missing_skills: list[str] = Field(
        description="Skills in this category the job calls for that the resume lacks."
    )


class MatchingProject(BaseModel):
    """A project from the resume that is relevant to the job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(description="The title of the matching project.")
    relevance_score: int = Field(
        ge=0,
        le=100,
        description="How relevant this project is to the job description (0-100).",
    )
    reason: str = Field(description="Why this project is considered relevant.")


class ResumeImprovement(BaseModel):
    """A suggested improvement to a specific section of the resume."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The resume section this recommendation applies to.")
    recommendation: str = Field(description="The recommended change to that section.")
    priority: int = Field(description="The priority of this recommendation relative to others.")


class ResumeAnalysisResult(BaseModel):
    """Structured outcome of analyzing a resume against a job description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_assessment: OverallAssessment = Field(
        description="The top-level summary of the resume's fit for the job description."
    )
    skill_matches: list[SkillMatch] = Field(
        description="Fit assessment broken down by skill category."
    )
    matching_projects: list[MatchingProject] = Field(
        description="Resume projects relevant to the job description."
    )
    strengths: list[str] = Field(
        description="Aspects of the resume that align well with the job description."
    )
    weaknesses: list[str] = Field(
        description="Aspects of the resume that fall short relative to the job description."
    )
    resume_improvements: list[ResumeImprovement] = Field(
        description="Recommended improvements to the resume."
    )
