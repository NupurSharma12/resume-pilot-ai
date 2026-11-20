"""Domain model: the result shape of a resume analysis.

`ResumeAnalysisResult` and its nested models describe what a resume
analysis *produces*, as a set of plain, nested data contracts. They contain
no logic for how that result is computed (no scoring, no skill matching,
no parsing) — that will live in the parser and any agents that construct
instances of these models.
"""

from pydantic import BaseModel, ConfigDict, Field


class CandidateProfile(BaseModel):
    """Identity details extracted from the resume itself.

    Distinct from the rest of this module: every other model here describes
    the *fit* between a resume and a job description, whereas this is a
    plain read of who the resume belongs to. It lives on
    `ResumeAnalysisResult` anyway because the analysis call is the only
    point where the full resume text is already in front of a model --
    extracting it here costs nothing extra, versus a second call purely to
    re-read the header.

    Only `name` is required. The rest are genuinely optional: plenty of
    resumes omit a current employer, state no title, or give no basis for
    a total-years figure, and inventing one is worse than leaving it unset
    (see `toCandidate` on the frontend, which renders a neutral
    "unavailable" state rather than a placeholder).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="The candidate's full name as it appears on the resume.")
    current_company: str | None = Field(
        default=None, description="Most recent employer. Null if not stated."
    )
    title: str | None = Field(
        default=None, description="Most recent job title. Null if not stated."
    )
    years_experience: int | None = Field(
        default=None,
        ge=0,
        description="Total years of professional experience. Null if not derivable.",
    )


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

    # `default=None` is load-bearing, not stylistic: every analysis
    # persisted before this field existed is stored verbatim as JSONB
    # (`job_preparations.analysis_result`) and is re-validated through this
    # model on every History read. Combined with `extra="forbid"` above,
    # making this required would turn every pre-existing record into a
    # ValidationError -- i.e. History would break for all historical data,
    # with no migration able to recover a name nobody extracted at the
    # time. New analyses populate it; old ones stay None forever.
    candidate_profile: CandidateProfile | None = Field(
        default=None,
        description="Identity details extracted from the resume.",
    )
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
