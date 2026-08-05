"""Unit tests for `TailoringWorkflow`.

Uses a small in-test fake `LLMGateway` (matching `FakeGateway` in
`test_career_conversation_workflow.py`'s pattern) that returns a
pre-programmed sequence of responses — a `TailoringPlan` for the first
`generate_structured` call (the Planner, Stage 2), then one
`TailoredSection` per planned change for the Rewrite Engine (Stage 3),
one `generate_structured` call each, scoped to that change's approved
evidence only. `MockGateway` isn't used here for the same reason it isn't
used for Career Conversation: its generic, type-driven placeholders can't
satisfy this workflow's evidence-id cross-object invariants.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.gateways.llm.models import LLMRequest, LLMResponse
from app.models.career_conversation import ConversationExchange
from app.models.resume_analysis import (
    HiringRecommendation,
    OverallAssessment,
    ResumeAnalysisResult,
    SkillMatch,
)
from app.models.tailored_resume import TailoredBullet, TailoredSection
from app.models.tailoring_plan import PlannedChange, TailoringAction, TailoringPlan
from app.prompts.resume_rewrite_prompt_builder import ResumeRewritePromptBuilder
from app.prompts.tailoring_planner_prompt_builder import TailoringPlannerPromptBuilder
from app.workflows.tailoring_workflow import TailoringPlanInvalidEvidenceError, TailoringWorkflow


class FakeGateway:
    """Structurally satisfies `LLMGateway`, returning a pre-programmed response sequence."""

    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("Unused by TailoringWorkflow.")

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]):
        assert self._responses, "FakeGateway called more times than responses were programmed."
        self.call_count += 1
        self.requests.append(request)
        return self._responses.pop(0)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        raise NotImplementedError("Unused by TailoringWorkflow.")
        yield  # pragma: no cover - makes this an async generator


@pytest.fixture
def resume_analysis() -> ResumeAnalysisResult:
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=70,
            hiring_recommendation=HiringRecommendation(decision="Proceed", reason="Solid fit."),
            summary="Solid fit overall.",
        ),
        skill_matches=[
            SkillMatch(category="Backend", score=80, matched_skills=["Python"], missing_skills=[]),
        ],
        matching_projects=[],
        strengths=["Strong backend ownership."],
        weaknesses=["Frontend experience is unclear."],
        resume_improvements=[],
    )


@pytest.fixture
def conversation_history() -> list[ConversationExchange]:
    return [
        ConversationExchange(
            topic="Frontend",
            question="Have you built any UI applications?",
            answer="I built the internal dashboard using React and TypeScript.",
            assistant_response=None,
        ),
    ]


def _workflow(gateway: FakeGateway) -> TailoringWorkflow:
    return TailoringWorkflow(
        evidence_store_builder=EvidenceStoreBuilder(),
        planner_prompt_builder=TailoringPlannerPromptBuilder(),
        rewrite_prompt_builder=ResumeRewritePromptBuilder(),
        gateway=gateway,
    )


async def test_full_pipeline_happy_path(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing from the summary.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Built the internal dashboard using React and TypeScript.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, section])
    workflow = _workflow(gateway)

    result = await workflow.tailor(
        resume="Backend engineer with Python experience.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
    )

    assert gateway.call_count == 2
    assert result.tailoring_plan.changes[0].section == "Summary"
    assert result.validation_report.passed is True
    assert result.validation_report.accepted_count == 1
    assert len(result.tailored_resume.sections) == 1
    assert result.evidence_store.get("conversation-turn-1") is not None


async def test_one_rewrite_call_is_made_per_planned_change(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing.",
                evidence_ids=["conversation-turn-1"],
            ),
            PlannedChange(
                section="Experience",
                action=TailoringAction.ADD_EMPHASIS,
                reason="Backend strength should be foregrounded.",
                evidence_ids=["analysis-strength-1"],
            ),
        ]
    )
    summary_section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Built the internal dashboard using React and TypeScript.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    experience_section = TailoredSection(
        heading="Experience",
        bullets=[
            TailoredBullet(
                text="Demonstrated strong backend ownership.",
                supporting_evidence_ids=["analysis-strength-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, summary_section, experience_section])
    workflow = _workflow(gateway)

    result = await workflow.tailor(
        resume="Backend engineer.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
    )

    # One planning call + one rewrite call per change (two changes).
    assert gateway.call_count == 3
    assert result.validation_report.accepted_count == 2
    assert {section.heading for section in result.tailored_resume.sections} == {
        "Summary",
        "Experience",
    }


async def test_rewrite_request_for_one_change_only_embeds_that_changes_approved_evidence(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """The Rewrite Engine's prompt must not contain evidence outside what its change approved.

    Structural proof (not just a validator-level check) that the Rewrite
    Engine cannot see, and therefore cannot cite, evidence the Planner
    didn't approve for a given change -- `analysis-strength-1` exists in
    the Evidence Store (there's a real "Strong backend ownership."
    strength on the fixture's resume analysis) but this change only
    approved `conversation-turn-1`, so it must never appear in the
    rewrite request's prompt text.
    """
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Built the internal dashboard using React and TypeScript.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, section])
    workflow = _workflow(gateway)

    await workflow.tailor(
        resume="Backend engineer.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
    )

    rewrite_request = gateway.requests[1]
    assert "conversation-turn-1" in rewrite_request.user_prompt
    assert "analysis-strength-1" not in rewrite_request.user_prompt
    assert "Strong backend ownership" not in rewrite_request.user_prompt


async def test_plan_citing_no_evidence_raises_before_rewrite_call(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    bad_plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Some reason.",
                evidence_ids=[],
            )
        ]
    )
    gateway = FakeGateway([bad_plan])
    workflow = _workflow(gateway)

    with pytest.raises(TailoringPlanInvalidEvidenceError):
        await workflow.tailor(
            resume="Backend engineer.",
            job_description="Looking for a full-stack engineer.",
            resume_analysis=resume_analysis,
            conversation_history=conversation_history,
        )

    # The Rewrite Engine must never be called against a plan that failed
    # its own evidence check.
    assert gateway.call_count == 1


async def test_plan_citing_unknown_evidence_id_raises(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    bad_plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Some reason.",
                evidence_ids=["conversation-turn-99"],
            )
        ]
    )
    gateway = FakeGateway([bad_plan])
    workflow = _workflow(gateway)

    with pytest.raises(TailoringPlanInvalidEvidenceError, match="conversation-turn-99"):
        await workflow.tailor(
            resume="Backend engineer.",
            job_description="Looking for a full-stack engineer.",
            resume_analysis=resume_analysis,
            conversation_history=conversation_history,
        )

    assert gateway.call_count == 1


async def test_rewrite_bullets_that_fail_validation_are_dropped_not_raised(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """The pipeline completes even when Validation rejects a bullet -- rejection isn't an error."""
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                # "Kubernetes" is a hallucination -- never in the cited evidence.
                text="Deployed the dashboard to Kubernetes.",
                supporting_evidence_ids=["conversation-turn-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, section])
    workflow = _workflow(gateway)

    result = await workflow.tailor(
        resume="Backend engineer.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
    )

    assert result.validation_report.passed is False
    assert result.validation_report.rejected_count == 1
    assert result.tailored_resume.sections == []


async def test_rewrite_citing_evidence_not_approved_for_its_own_change_is_rejected(
    resume_analysis: ResumeAnalysisResult, conversation_history: list[ConversationExchange]
) -> None:
    """Defense in depth: even if a model somehow cites real evidence outside its scope, reject it.

    The restricted prompt (see `test_rewrite_request_for_one_change_only_embeds_that_changes_
    approved_evidence`) should make this unreachable in practice, but
    Stage 4 must independently enforce the same rule -- this simulates a
    `FakeGateway` "misbehaving" the way real prompt drift could, and
    proves the pipeline still catches it.
    """
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.REWRITE,
                reason="Recent frontend work is missing.",
                evidence_ids=["conversation-turn-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Demonstrated strong backend ownership.",
                # Real evidence id ("analysis-strength-1" exists in the
                # store, from resume_analysis.strengths) but never
                # approved for *this* change.
                supporting_evidence_ids=["analysis-strength-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, section])
    workflow = _workflow(gateway)

    result = await workflow.tailor(
        resume="Backend engineer.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=conversation_history,
    )

    assert result.validation_report.passed is False
    assert result.validation_report.rejected_count == 1
    assert "analysis-strength-1" in result.validation_report.rejected_bullets[0].reason
    assert "did not approve" in result.validation_report.rejected_bullets[0].reason
    assert result.tailored_resume.sections == []


async def test_empty_conversation_history_still_produces_a_usable_evidence_store(
    resume_analysis: ResumeAnalysisResult,
) -> None:
    plan = TailoringPlan(
        changes=[
            PlannedChange(
                section="Summary",
                action=TailoringAction.ADD_EMPHASIS,
                reason="Backend strength should be foregrounded.",
                evidence_ids=["analysis-strength-1"],
            )
        ]
    )
    section = TailoredSection(
        heading="Summary",
        bullets=[
            TailoredBullet(
                text="Demonstrated strong backend ownership.",
                supporting_evidence_ids=["analysis-strength-1"],
            )
        ],
    )
    gateway = FakeGateway([plan, section])
    workflow = _workflow(gateway)

    result = await workflow.tailor(
        resume="Backend engineer.",
        job_description="Looking for a full-stack engineer.",
        resume_analysis=resume_analysis,
        conversation_history=[],
    )

    assert result.validation_report.passed is True
    assert result.evidence_store.get("analysis-strength-1") is not None
