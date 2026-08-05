"""Tailoring Engine workflow: orchestrates the full Evidence-Based Resume Tailoring pipeline.

`TailoringWorkflow` composes five collaborators — an `EvidenceStoreBuilder`,
two prompt builders (Planner, Rewrite Engine), an `LLMGateway`, and the
pure-Python `validate_tailored_resume` function — into the pipeline this
sprint specifies end to end:

    Evidence Store -> Tailoring Planner -> Resume Rewrite Engine -> Validation

Exactly one of those four stages is not an LLM call: Evidence Store
construction (Stage 1, pure aggregation) and Validation (Stage 4, pure
checking) are both deterministic Python, by design — see their own
modules' docstrings for why. Only the Planner (Stage 2, decide what/why)
and the Rewrite Engine (Stage 3, decide how to phrase it) call the
gateway.

The Planner call happens once, against the whole Evidence Store — it is
this pipeline's single authority on what evidence may be used at all (see
`TailoringPlannerPromptBuilder`). The Rewrite Engine call happens once
*per planned change*, not once for the whole plan, and each call is
scoped (via `ResumeRewritePromptBuilder`) to only that change's approved
evidence ids — the Rewrite Engine never sees the full Evidence Store, so
it cannot cite a fact the Planner didn't approve for that specific
change, structurally, not merely by instruction. Stage 4 then re-checks
that guarantee explicitly (`_validate`, via `RewrittenChange` pairing each
rewritten section back to the change that produced it) as defense in
depth, the same "don't just ask nicely, verify" philosophy this codebase
already applies elsewhere (see `CareerConversationWorkflow._validate_decision`).

Logs each stage's start/completion at INFO (with elapsed time), and logs
(then re-raises) structured-output validation failures at ERROR — the
same pattern `ResumeAnalysisWorkflow`/`CareerConversationWorkflow` use.
Never logs resume/job-description/evidence/plan/bullet content — only
counts, ids-as-counts, and lifecycle events.
"""

import time
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.logging import get_logger
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.evidence.tailoring_validator import RewrittenChange, validate_tailored_resume
from app.gateways.llm.gateway import LLMGateway
from app.models.career_conversation import ConversationExchange
from app.models.evidence_store import EvidenceStore
from app.models.resume_analysis import ResumeAnalysisResult
from app.models.tailored_resume import TailoredResume, TailoredSection, ValidationReport
from app.models.tailoring_plan import TailoringPlan
from app.prompts.resume_rewrite_prompt_builder import ResumeRewritePromptBuilder
from app.prompts.tailoring_planner_prompt_builder import TailoringPlannerPromptBuilder

logger = get_logger(__name__)


class TailoringPlanInvalidEvidenceError(RuntimeError):
    """Raised when a `TailoringPlan` cites evidence that doesn't exist, or cites none at all.

    A `ValidationError` from `generate_structured` means the LLM's output
    didn't match `TailoringPlan`'s *schema*. This is a different failure:
    the output was perfectly valid Pydantic (every `PlannedChange` has a
    `section`/`action`/`reason`/`evidence_ids`), but violates the one
    cross-object rule no single field's own validation can express —
    every cited id must actually exist in this request's `EvidenceStore`,
    and there must be at least one. Modeling it as its own exception
    (mirroring `ConversationTurnInconsistentError`'s precedent) makes this
    specific contract violation identifiable to callers and log readers,
    distinct from a schema mismatch.
    """


@dataclass(frozen=True)
class TailoringResult:
    """The full output of one tailoring run: every stage's result, bundled together.

    A plain dataclass, not a Pydantic model: none of this is ever passed
    to `generate_structured` or deserialized from external input — it's
    purely an in-process return value the endpoint reads from and maps
    onto the API response (which exposes `tailoring_plan`, `tailored_resume`,
    and `validation_report`, but deliberately not `evidence_store` — see
    `tailor_resume.py`). `evidence_store` is still included here so tests
    (and any future caller) can inspect exactly what evidence a given run
    was grounded in.
    """

    evidence_store: EvidenceStore
    tailoring_plan: TailoringPlan
    tailored_resume: TailoredResume
    validation_report: ValidationReport


class TailoringWorkflow:
    """Orchestrates the Tailoring Engine pipeline by composing five collaborators.

    All five are supplied by the caller (constructor injection), matching
    `ResumeAnalysisWorkflow`/`CareerConversationWorkflow`'s established
    pattern: this class depends on their interfaces, but owns none of
    their implementation details.
    """

    def __init__(
        self,
        evidence_store_builder: EvidenceStoreBuilder,
        planner_prompt_builder: TailoringPlannerPromptBuilder,
        rewrite_prompt_builder: ResumeRewritePromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        self._evidence_store_builder = evidence_store_builder
        self._planner_prompt_builder = planner_prompt_builder
        self._rewrite_prompt_builder = rewrite_prompt_builder
        self._gateway = gateway

    async def tailor(
        self,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        conversation_history: list[ConversationExchange],
    ) -> TailoringResult:
        """Run the full pipeline and return every stage's result.

        `conversation_history` may be empty (see `EvidenceStoreBuilder.build`)
        — a Career Conversation session is useful additional evidence, not
        a hard prerequisite for tailoring.
        """
        logger.info("tailoring_started")
        pipeline_start = time.perf_counter()

        evidence_store = self._build_evidence_store(
            resume, job_description, resume_analysis, conversation_history
        )
        plan = await self._generate_plan(job_description, resume_analysis, evidence_store)
        rewritten_changes = await self._generate_rewrite(resume, plan, evidence_store)
        tailored_resume, validation_report = self._validate(rewritten_changes, evidence_store)

        elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info(
            "tailoring_completed",
            elapsed_ms=elapsed_ms,
            change_count=len(plan.changes),
            accepted_bullet_count=validation_report.accepted_count,
            rejected_bullet_count=validation_report.rejected_count,
        )
        return TailoringResult(
            evidence_store=evidence_store,
            tailoring_plan=plan,
            tailored_resume=tailored_resume,
            validation_report=validation_report,
        )

    def _build_evidence_store(
        self,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        conversation_history: list[ConversationExchange],
    ) -> EvidenceStore:
        start = time.perf_counter()
        evidence_store = self._evidence_store_builder.build(
            resume, job_description, resume_analysis, conversation_history
        )
        logger.info(
            "evidence_store_built",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            evidence_item_count=len(evidence_store.items),
            conversation_turn_count=len(conversation_history),
        )
        return evidence_store

    async def _generate_plan(
        self,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        evidence_store: EvidenceStore,
    ) -> TailoringPlan:
        start = time.perf_counter()
        request = self._planner_prompt_builder.build(
            job_description, resume_analysis, evidence_store
        )
        try:
            plan = await self._gateway.generate_structured(request, TailoringPlan)
        except ValidationError as exc:
            logger.error("tailoring_plan_validation_failed", error=str(exc))
            raise
        self._validate_plan_evidence(plan, evidence_store)
        logger.info(
            "tailoring_plan_generated",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            change_count=len(plan.changes),
        )
        return plan

    async def _generate_rewrite(
        self, resume: str, plan: TailoringPlan, evidence_store: EvidenceStore
    ) -> list[RewrittenChange]:
        """Call the Rewrite Engine once per planned change, each scoped to only its own evidence.

        One `generate_structured(..., TailoredSection)` call per
        `PlannedChange`, not one call for the whole plan — see this
        module's docstring on why: `ResumeRewritePromptBuilder.build`
        only embeds `change.evidence_ids`' evidence, so each call is
        structurally incapable of citing evidence outside what that one
        change was approved to use.
        """
        start = time.perf_counter()
        rewritten_changes: list[RewrittenChange] = []
        for change in plan.changes:
            request = self._rewrite_prompt_builder.build(resume, change, evidence_store)
            try:
                section = await self._gateway.generate_structured(request, TailoredSection)
            except ValidationError as exc:
                logger.error("resume_rewrite_validation_failed", error=str(exc))
                raise
            rewritten_changes.append(RewrittenChange(change=change, section=section))

        logger.info(
            "resume_rewritten",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            section_count=len(rewritten_changes),
            bullet_count=sum(len(rc.section.bullets) for rc in rewritten_changes),
        )
        return rewritten_changes

    def _validate(
        self, rewritten_changes: list[RewrittenChange], evidence_store: EvidenceStore
    ) -> tuple[TailoredResume, ValidationReport]:
        start = time.perf_counter()
        tailored_resume, report = validate_tailored_resume(rewritten_changes, evidence_store)
        logger.info(
            "validation_completed",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            total_bullets=report.total_bullets,
            accepted_count=report.accepted_count,
            rejected_count=report.rejected_count,
            passed=report.passed,
        )
        return tailored_resume, report

    @staticmethod
    def _validate_plan_evidence(plan: TailoringPlan, evidence_store: EvidenceStore) -> None:
        """Enforce that every planned change cites at least one real evidence id.

        Checked explicitly here, in the workflow, rather than as a
        `model_validator` on `TailoringPlan` itself — same reasoning as
        `CareerConversationWorkflow._validate_decision`: this check spans
        two objects (the plan and the evidence store it must be grounded
        in), which no single model's own validation can express. This is
        also what makes the Rewrite Engine's restricted evidence catalog
        (see `_generate_rewrite`) safe to build directly from
        `change.evidence_ids`: by the time any rewrite call happens, every
        id in every change is already known to exist in `evidence_store`.
        """
        for change in plan.changes:
            if not change.evidence_ids:
                raise TailoringPlanInvalidEvidenceError(
                    f"Planned change for section {change.section!r} cites no evidence."
                )
            unknown_ids = evidence_store.unknown_ids(change.evidence_ids)
            if unknown_ids:
                raise TailoringPlanInvalidEvidenceError(
                    f"Planned change for section {change.section!r} cites unknown evidence "
                    f"id(s): {', '.join(unknown_ids)}."
                )
