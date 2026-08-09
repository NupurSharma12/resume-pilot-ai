"""Deterministically compares two resume analyses -- the Post-Apply Analysis Loop's core.

`compute_resume_analysis_comparison` is pure domain logic: no LLM call, no
I/O, no randomness. It exists specifically so a numeric score change is
never left to an LLM to characterize (see
`docs/features/postapply-analysis-loop.md`'s "be honest about the
result" requirement) -- `after > before` is `improved`, `after == before`
is `unchanged`, `after < before` is `decreased`, full stop.

Only reuses information already present in the two `ResumeAnalysisResult`s
passed in (their `overall_assessment.overall_score`, `skill_matches`,
`strengths`, `weaknesses`) -- nothing here invents a claim, a category, or
a gap that neither analysis actually reported.
"""

from app.models.analysis_comparison import (
    ComparisonStatus,
    ResumeAnalysisComparison,
    SkillCategoryComparison,
)
from app.models.resume_analysis import ResumeAnalysisResult


def _status_for(delta: int) -> ComparisonStatus:
    if delta > 0:
        return ComparisonStatus.IMPROVED
    if delta < 0:
        return ComparisonStatus.DECREASED
    return ComparisonStatus.UNCHANGED


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _diff_preserving_order(source: list[str], exclude: list[str]) -> list[str]:
    """Every item in `source` that is not also in `exclude`, in `source`'s own order."""
    excluded = set(exclude)
    return _dedupe_preserving_order([item for item in source if item not in excluded])


def _compare_categories(
    before: ResumeAnalysisResult, after: ResumeAnalysisResult
) -> list[SkillCategoryComparison]:
    after_by_category = {skill_match.category: skill_match for skill_match in after.skill_matches}

    comparisons: list[SkillCategoryComparison] = []
    for before_match in before.skill_matches:
        after_match = after_by_category.get(before_match.category)
        if after_match is None:
            # A category present only in the before analysis has nothing to
            # compare against -- it isn't silently dropped, it just has no
            # place in a *category* comparison; the resume-wide
            # strengths/weaknesses diff below is where a genuine regression
            # like this would still surface if it's also reflected there.
            continue

        delta = after_match.score - before_match.score
        comparisons.append(
            SkillCategoryComparison(
                category=before_match.category,
                score_before=before_match.score,
                score_after=after_match.score,
                score_delta=delta,
                status=_status_for(delta),
                newly_matched_skills=_diff_preserving_order(
                    after_match.matched_skills, before_match.matched_skills
                ),
                newly_missing_skills=_diff_preserving_order(
                    before_match.matched_skills, after_match.matched_skills
                ),
            )
        )
    return comparisons


def compute_resume_analysis_comparison(
    before: ResumeAnalysisResult, after: ResumeAnalysisResult
) -> ResumeAnalysisComparison:
    """Compare `before` (the original analysis) against `after` (the post-apply re-analysis).

    Both must be real, completed `ResumeAnalysisResult`s -- callers must
    never invoke this with a fabricated or partial result (see the
    `/reanalyze` endpoint's failure handling, which never calls this
    function at all if re-analysis itself failed).
    """
    score_before = before.overall_assessment.overall_score
    score_after = after.overall_assessment.overall_score
    score_delta = score_after - score_before

    return ResumeAnalysisComparison(
        score_before=score_before,
        score_after=score_after,
        score_delta=score_delta,
        status=_status_for(score_delta),
        category_comparisons=_compare_categories(before, after),
        strengths_gained=_diff_preserving_order(after.strengths, before.strengths),
        strengths_lost=_diff_preserving_order(before.strengths, after.strengths),
        weaknesses_resolved=_diff_preserving_order(before.weaknesses, after.weaknesses),
        weaknesses_remaining=_diff_preserving_order(
            [w for w in before.weaknesses if w in after.weaknesses], []
        ),
        new_weaknesses=_diff_preserving_order(after.weaknesses, before.weaknesses),
    )
