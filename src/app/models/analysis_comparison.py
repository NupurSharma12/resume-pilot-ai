"""Domain model: a deterministic before/after comparison of two resume analyses.

`ResumeAnalysisComparison` and its nested models describe the *result* of
comparing two `ResumeAnalysisResult`s (see `app.analysis.comparison` for
the pure function that produces one) — the post-apply optimization loop's
answer to "did the changes actually improve the match?" (see
`docs/features/postapply-analysis-loop.md`). Like `resume_analysis.py`,
this module holds no computation, only the shape of the answer.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ComparisonStatus(StrEnum):
    """The one honest, deterministic verdict a score comparison can reach.

    Computed purely from `after_score` vs. `before_score` (see
    `app.analysis.comparison.compute_resume_analysis_comparison`) — never
    inferred by an LLM. `UNCHANGED` and `DECREASED` are first-class
    outcomes, not edge cases folded into `IMPROVED`: this product must
    never present "nothing got better" or "it got worse" as a success.
    """

    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    DECREASED = "decreased"


class SkillCategoryComparison(BaseModel):
    """Before/after comparison for one skill category present in both analyses.

    Only categories that appear (by `category` name) in *both* analyses
    are represented here — see `compute_resume_analysis_comparison` for
    how a category present in only one side is handled (surfaced via the
    parent comparison's own strengths/weaknesses diff instead, never
    silently dropped).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(description="The skill category being compared.")
    score_before: int = Field(description="This category's fit score before applying changes.")
    score_after: int = Field(description="This category's fit score after applying changes.")
    score_delta: int = Field(description="score_after - score_before.")
    status: ComparisonStatus = Field(description="Deterministic verdict for this category alone.")
    newly_matched_skills: list[str] = Field(
        description="Skills matched after, but not before -- evidence of real improvement."
    )
    newly_missing_skills: list[str] = Field(
        description=(
            "Skills matched before but missing after -- a regression signal: this category "
            "used to demonstrate a skill the resume no longer shows."
        )
    )


class ResumeAnalysisComparison(BaseModel):
    """The full, honest before/after comparison of a resume against one job description.

    Never fabricated: an instance of this model must only ever be built
    from two real `ResumeAnalysisResult`s that both actually completed
    (see the `/reanalyze` endpoint's failure handling) -- there is no
    default/empty comparison to fall back to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    score_before: int = Field(description="Overall fit score before applying changes.")
    score_after: int = Field(description="Overall fit score after applying changes.")
    score_delta: int = Field(description="score_after - score_before.")
    status: ComparisonStatus = Field(
        description="improved iff score_after > score_before; decreased iff <; unchanged iff ==."
    )
    category_comparisons: list[SkillCategoryComparison] = Field(
        description="Per-category comparisons, for every category present in both analyses."
    )
    strengths_gained: list[str] = Field(description="Strengths present after, but not before.")
    strengths_lost: list[str] = Field(
        description="Strengths present before, but no longer present after -- a regression signal."
    )
    weaknesses_resolved: list[str] = Field(
        description="Weaknesses present before that no longer appear after."
    )
    weaknesses_remaining: list[str] = Field(
        description="Weaknesses present in both before and after -- still unaddressed."
    )
    new_weaknesses: list[str] = Field(
        description="Weaknesses present after, but not before -- a regression signal."
    )
