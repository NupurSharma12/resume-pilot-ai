"""Unit tests for the deterministic before/after resume-analysis comparator.

Covers the Post-Apply Analysis Loop's core invariant (see
`docs/features/postapply-analysis-loop.md`): `after > before` is
`improved`, `after == before` is `unchanged`, `after < before` is
`decreased` -- never an LLM's opinion. Also covers category-level and
strengths/weaknesses diffs, which reuse the analyses' own existing
structured data rather than inventing anything new.
"""

import pytest
from pydantic import ValidationError

from app.analysis.comparison import compute_resume_analysis_comparison
from app.models.analysis_comparison import ComparisonStatus
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
    SkillMatch,
)


def _analysis(
    score: int,
    *,
    skill_matches: list[SkillMatch] | None = None,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=score,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=skill_matches or [],
        matching_projects=[],
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        resume_improvements=[],
    )


def test_score_increase_is_improved_with_correct_delta() -> None:
    comparison = compute_resume_analysis_comparison(_analysis(80), _analysis(85))

    assert comparison.score_before == 80
    assert comparison.score_after == 85
    assert comparison.score_delta == 5
    assert comparison.status == ComparisonStatus.IMPROVED


def test_unchanged_score_is_unchanged_with_zero_delta() -> None:
    comparison = compute_resume_analysis_comparison(_analysis(80), _analysis(80))

    assert comparison.score_delta == 0
    assert comparison.status == ComparisonStatus.UNCHANGED


def test_score_decrease_is_decreased_with_negative_delta() -> None:
    comparison = compute_resume_analysis_comparison(_analysis(80), _analysis(75))

    assert comparison.score_delta == -5
    assert comparison.status == ComparisonStatus.DECREASED


def test_comparison_never_asks_an_llm_and_is_pure_score_arithmetic() -> None:
    # Same inputs, called twice -- a pure function must return an
    # equivalent result both times, with no hidden state or randomness.
    before, after = _analysis(60), _analysis(70)
    first = compute_resume_analysis_comparison(before, after)
    second = compute_resume_analysis_comparison(before, after)

    assert first == second
    assert first.status == ComparisonStatus.IMPROVED


def test_category_comparison_reports_score_delta_and_status_per_category() -> None:
    before = _analysis(
        70,
        skill_matches=[
            SkillMatch(category="Backend", score=80, matched_skills=["Python"], missing_skills=[]),
            SkillMatch(category="Frontend", score=40, matched_skills=[], missing_skills=["React"]),
        ],
    )
    after = _analysis(
        75,
        skill_matches=[
            SkillMatch(category="Backend", score=80, matched_skills=["Python"], missing_skills=[]),
            SkillMatch(category="Frontend", score=60, matched_skills=["React"], missing_skills=[]),
        ],
    )

    comparison = compute_resume_analysis_comparison(before, after)
    by_category = {c.category: c for c in comparison.category_comparisons}

    assert by_category["Backend"].status == ComparisonStatus.UNCHANGED
    assert by_category["Backend"].score_delta == 0
    assert by_category["Frontend"].status == ComparisonStatus.IMPROVED
    assert by_category["Frontend"].score_delta == 20
    assert by_category["Frontend"].newly_matched_skills == ["React"]
    assert by_category["Frontend"].newly_missing_skills == []


def test_category_present_only_before_is_omitted_from_category_comparisons() -> None:
    before = _analysis(
        70,
        skill_matches=[
            SkillMatch(category="DevOps", score=50, matched_skills=["Docker"], missing_skills=[]),
        ],
    )
    after = _analysis(70, skill_matches=[])

    comparison = compute_resume_analysis_comparison(before, after)

    assert comparison.category_comparisons == []


def test_regression_in_a_category_is_visible_as_newly_missing_skills() -> None:
    before = _analysis(
        80,
        skill_matches=[
            SkillMatch(
                category="Backend", score=90, matched_skills=["Python", "SQL"], missing_skills=[]
            ),
        ],
    )
    after = _analysis(
        75,
        skill_matches=[
            SkillMatch(
                category="Backend", score=70, matched_skills=["Python"], missing_skills=["SQL"]
            ),
        ],
    )

    comparison = compute_resume_analysis_comparison(before, after)
    backend = comparison.category_comparisons[0]

    assert backend.status == ComparisonStatus.DECREASED
    assert backend.newly_missing_skills == ["SQL"]
    assert backend.newly_matched_skills == []


def test_strengths_and_weaknesses_are_diffed_without_inventing_content() -> None:
    before = _analysis(
        70,
        strengths=["Strong backend ownership."],
        weaknesses=["Frontend experience is unclear.", "No leadership evidence."],
    )
    after = _analysis(
        80,
        strengths=["Strong backend ownership.", "Demonstrated frontend work."],
        weaknesses=["No leadership evidence."],
    )

    comparison = compute_resume_analysis_comparison(before, after)

    assert comparison.strengths_gained == ["Demonstrated frontend work."]
    assert comparison.strengths_lost == []
    assert comparison.weaknesses_resolved == ["Frontend experience is unclear."]
    assert comparison.weaknesses_remaining == ["No leadership evidence."]
    assert comparison.new_weaknesses == []


def test_lost_strength_and_new_weakness_are_surfaced_as_regressions() -> None:
    before = _analysis(80, strengths=["Strong backend ownership."], weaknesses=[])
    after = _analysis(
        75, strengths=[], weaknesses=["Resume no longer demonstrates ownership clearly."]
    )

    comparison = compute_resume_analysis_comparison(before, after)

    assert comparison.strengths_lost == ["Strong backend ownership."]
    assert comparison.new_weaknesses == ["Resume no longer demonstrates ownership clearly."]


def test_missing_overall_score_is_rejected_before_it_can_reach_the_comparator() -> None:
    # compute_resume_analysis_comparison only ever operates on a real,
    # already-validated ResumeAnalysisResult -- there is no "missing
    # score" case for it to handle, because OverallAssessment itself
    # cannot be constructed without one.
    with pytest.raises(ValidationError):
        OverallAssessment(
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        )  # type: ignore[call-arg]


def test_invalid_out_of_range_score_is_rejected_before_it_can_reach_the_comparator() -> None:
    with pytest.raises(ValidationError):
        OverallAssessment(
            overall_score=150,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        )


def test_empty_strengths_and_weaknesses_on_both_sides_produce_empty_diffs() -> None:
    comparison = compute_resume_analysis_comparison(_analysis(70), _analysis(70))

    assert comparison.strengths_gained == []
    assert comparison.strengths_lost == []
    assert comparison.weaknesses_resolved == []
    assert comparison.weaknesses_remaining == []
    assert comparison.new_weaknesses == []
    assert comparison.category_comparisons == []
