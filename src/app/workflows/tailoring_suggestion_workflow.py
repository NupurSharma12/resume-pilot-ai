"""Tailoring Suggestion workflow: orchestrates the Evidence-Based Interactive Tailoring pipeline.

`TailoringSuggestionWorkflow` composes the resume structure parser, an
`EvidenceStoreBuilder`, two prompt builders (Planner, Rewrite Engine), and
an `LLMGateway` into the pipeline this feature specifies end to end:

    Resume Structure -> Evidence Store -> Suggestion Planner -> Suggestion Rewrite -> Validation

This is the finer-grained successor to `TailoringWorkflow` (superseded —
see `docs/features/tailoring-engine.md`): the same "planner decides,
rewrite engine executes, evidence scoped per call" shape, just anchored
to one resume item per suggestion instead of one whole section per
change. The Planner call happens once, against the whole Evidence Store
(it is this pipeline's single authority on what evidence may be used at
all). The Rewrite Engine call happens once *per proposed edit*, and each
call is scoped to only that edit's approved evidence — never the full
catalog — so it is structurally incapable of citing a fact the Planner
didn't approve for that specific edit. Every resulting suggestion is
validated (`app.evidence.suggestion_validator`) before being returned, so
the review UI already knows which suggestions are soundly evidence-backed
before the user even decides.

Logs each stage's start/completion at INFO (with elapsed time), and logs
(then re-raises) structured-output validation failures at ERROR — the
same pattern every other workflow in this codebase uses. Never logs
resume/job-description/evidence/suggestion content — only counts and
lifecycle events.
"""

import time
import uuid
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.logging import get_logger
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.evidence.suggestion_validator import validate_suggestion
from app.gateways.llm.gateway import LLMGateway
from app.models.career_conversation import ConversationExchange
from app.models.evidence_store import EvidenceStore
from app.models.resume_analysis import ResumeAnalysisResult
from app.models.resume_structure import StructuredResume
from app.models.tailoring_suggestions import (
    PlannedEdits,
    SuggestedEdit,
    SuggestionPlan,
    SuggestionText,
    TailoringSuggestion,
)
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.tailoring.conflicts import compute_conflicts

logger = get_logger(__name__)

# A suggestion only starts pre-selected if it's both soundly evidence-backed
# (see `app.evidence.suggestion_validator`) and the model itself reported
# reasonable confidence -- a low-confidence but technically-passing
# suggestion still shows up for review, just not pre-checked.
_SELECTED_BY_DEFAULT_CONFIDENCE_THRESHOLD = 60

_CLEANLY_SUPPORTED_STATUSES = frozenset(
    {"supported_by_original_resume", "supported_by_conversation", "supported_by_both"}
)


class SuggestionPlanInvalidError(RuntimeError):
    """Raised when the Planner proposes an edit that violates its own contract.

    A `ValidationError` from `generate_structured` means the LLM's output
    didn't match `PlannedEdits`' *schema*. This is a different failure:
    the output was perfectly valid Pydantic, but cites an evidence id
    that doesn't exist, cites no evidence at all, or targets a resume
    item id that was never offered — cross-object rules no single
    field's own validation can express. Mirrors
    `TailoringPlanInvalidEvidenceError` from the superseded pipeline.
    """


@dataclass(frozen=True)
class SuggestionGenerationResult:
    """The full output of one suggestion-generation run.

    `structured_resume`/`evidence_store` are included so callers (the
    endpoint) can log/inspect them, but neither is ever serialized to the
    API response — the response exposes `plan` (via `TailoringPlanStore`
    and the response mapping) only.
    """

    structured_resume: StructuredResume
    evidence_store: EvidenceStore
    plan: SuggestionPlan


class TailoringSuggestionWorkflow:
    """Orchestrates the Interactive Tailoring pipeline by composing its collaborators.

    All collaborators are supplied by the caller (constructor injection),
    matching every other workflow in this codebase.
    """

    def __init__(
        self,
        structure_parser: ResumeStructureParser,
        evidence_store_builder: EvidenceStoreBuilder,
        planner_prompt_builder: SuggestionPlannerPromptBuilder,
        rewrite_prompt_builder: SuggestionRewritePromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        self._structure_parser = structure_parser
        self._evidence_store_builder = evidence_store_builder
        self._planner_prompt_builder = planner_prompt_builder
        self._rewrite_prompt_builder = rewrite_prompt_builder
        self._gateway = gateway

    async def generate_suggestions(
        self,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        conversation_history: list[ConversationExchange],
        custom_instructions: str | None,
    ) -> SuggestionGenerationResult:
        """Run the full pipeline and return the structured resume, evidence store, and plan.

        `conversation_history` may be empty and `custom_instructions` may
        be `None` — neither is a hard requirement; a candidate with only
        a resume and its analysis can still be tailored.
        """
        logger.info("suggestion_generation_started")
        pipeline_start = time.perf_counter()

        structured_resume = self._parse_resume(resume)
        evidence_store = self._build_evidence_store(
            structured_resume, resume, job_description, resume_analysis, conversation_history
        )
        edits = await self._generate_edits(
            job_description, resume_analysis, evidence_store, structured_resume, custom_instructions
        )
        suggestions = await self._generate_suggestion_texts(
            edits, structured_resume, evidence_store, custom_instructions
        )
        suggestions = self._annotate_conflicts(suggestions)
        plan = SuggestionPlan(plan_id=str(uuid.uuid4()), suggestions=suggestions)

        elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info(
            "suggestion_generation_completed",
            elapsed_ms=elapsed_ms,
            plan_id=plan.plan_id,
            suggestion_count=len(suggestions),
            selected_by_default_count=sum(1 for s in suggestions if s.selected_by_default),
        )
        return SuggestionGenerationResult(
            structured_resume=structured_resume, evidence_store=evidence_store, plan=plan
        )

    def _parse_resume(self, resume: str) -> StructuredResume:
        start = time.perf_counter()
        structured_resume = self._structure_parser.parse(resume)
        logger.info(
            "resume_structure_parsed",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            section_count=len(structured_resume.sections),
            item_count=sum(len(section.items) for section in structured_resume.sections),
        )
        return structured_resume

    def _build_evidence_store(
        self,
        structured_resume: StructuredResume,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        conversation_history: list[ConversationExchange],
    ) -> EvidenceStore:
        start = time.perf_counter()
        evidence_store = self._evidence_store_builder.build(
            structured_resume, resume, job_description, resume_analysis, conversation_history
        )
        logger.info(
            "evidence_store_built",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            evidence_item_count=len(evidence_store.items),
            conversation_turn_count=len(conversation_history),
        )
        return evidence_store

    async def _generate_edits(
        self,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        evidence_store: EvidenceStore,
        structured_resume: StructuredResume,
        custom_instructions: str | None,
    ) -> list[SuggestedEdit]:
        start = time.perf_counter()
        request = self._planner_prompt_builder.build(
            job_description, resume_analysis, evidence_store, structured_resume, custom_instructions
        )
        try:
            planned = await self._gateway.generate_structured(request, PlannedEdits)
        except ValidationError as exc:
            logger.error("suggestion_plan_validation_failed", error=str(exc))
            raise

        for edit in planned.edits:
            self._validate_edit_contract(edit, evidence_store, structured_resume)

        logger.info(
            "suggestion_plan_generated",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            edit_count=len(planned.edits),
        )
        return planned.edits

    @staticmethod
    def _validate_edit_contract(
        edit: SuggestedEdit, evidence_store: EvidenceStore, structured_resume: StructuredResume
    ) -> None:
        """Enforce that a planned edit targets a real item and cites at least one real id.

        Checked explicitly here, in the workflow, rather than as a model
        validator — this check spans multiple objects (the edit, the
        evidence store, and the resume structure), which no single
        model's own validation can express. Mirrors
        `TailoringWorkflow._validate_plan_evidence` from the superseded
        pipeline.
        """
        if structured_resume.get_item(edit.target_item_id) is None:
            raise SuggestionPlanInvalidError(
                f"Planned edit targets item {edit.target_item_id!r}, which does not exist "
                "in the resume."
            )
        if not edit.evidence_ids:
            raise SuggestionPlanInvalidError(
                f"Planned edit for item {edit.target_item_id!r} cites no evidence."
            )
        unknown_ids = evidence_store.unknown_ids(edit.evidence_ids)
        if unknown_ids:
            raise SuggestionPlanInvalidError(
                f"Planned edit for item {edit.target_item_id!r} cites unknown evidence "
                f"id(s): {', '.join(unknown_ids)}."
            )

    async def _generate_suggestion_texts(
        self,
        edits: list[SuggestedEdit],
        structured_resume: StructuredResume,
        evidence_store: EvidenceStore,
        custom_instructions: str | None,
    ) -> list[TailoringSuggestion]:
        start = time.perf_counter()
        suggestions: list[TailoringSuggestion] = []
        for index, edit in enumerate(edits):
            suggestion = await self._generate_one_suggestion(
                index, edit, structured_resume, evidence_store, custom_instructions
            )
            suggestions.append(suggestion)

        logger.info(
            "suggestion_texts_generated",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            suggestion_count=len(suggestions),
        )
        return suggestions

    @staticmethod
    def _annotate_conflicts(suggestions: list[TailoringSuggestion]) -> list[TailoringSuggestion]:
        """Populates each suggestion's `conflicts_with`, computed once over the whole plan.

        Uses the exact same `compute_conflicts` that
        `SuggestionApplier`/`DocxDocumentEditor` enforce at apply time, so
        the review UI's proactive "these are mutually exclusive" warning
        can never disagree with what apply actually rejects.

        Also downgrades `selected_by_default` for every suggestion but the
        first-seen one in each conflicting group -- without this, two
        suggestions that are genuine alternatives (e.g. two different
        rewordings of the same line) could both start pre-selected,
        making the default selection self-contradictory the moment the
        user clicked Apply without changing anything.
        """
        conflicts = compute_conflicts(suggestions)
        annotated: list[TailoringSuggestion] = []
        defaulted_ids: set[str] = set()
        for suggestion in suggestions:
            conflicts_with = conflicts.get(suggestion.suggestion_id, [])
            selected_by_default = suggestion.selected_by_default
            if selected_by_default and defaulted_ids.intersection(conflicts_with):
                selected_by_default = False
            if selected_by_default:
                defaulted_ids.add(suggestion.suggestion_id)
            annotated.append(
                suggestion.model_copy(
                    update={
                        "conflicts_with": conflicts_with,
                        "selected_by_default": selected_by_default,
                    }
                )
            )
        return annotated

    async def _generate_one_suggestion(
        self,
        index: int,
        edit: SuggestedEdit,
        structured_resume: StructuredResume,
        evidence_store: EvidenceStore,
        custom_instructions: str | None,
    ) -> TailoringSuggestion:
        from app.models.tailoring_suggestions import REPLACEMENT_OPERATIONS

        target_item = structured_resume.get_item(edit.target_item_id)
        assert target_item is not None  # guaranteed by `_validate_edit_contract`
        current_text = target_item.text if edit.operation in REPLACEMENT_OPERATIONS else None

        request = self._rewrite_prompt_builder.build(
            edit, current_text, evidence_store, custom_instructions
        )
        try:
            text_result = await self._gateway.generate_structured(request, SuggestionText)
        except ValidationError as exc:
            logger.error("suggestion_rewrite_validation_failed", error=str(exc))
            raise

        # Structural scoping, as defense in depth: the model was only
        # ever shown `edit.evidence_ids`' evidence (see
        # `SuggestionRewritePromptBuilder`), so it should be structurally
        # incapable of citing anything else -- but a model can still
        # hallucinate an id, so anything outside what was actually
        # offered is dropped here rather than trusted.
        approved_ids = set(edit.evidence_ids)
        cited_ids = [eid for eid in text_result.evidence_ids if eid in approved_ids]

        validation = validate_suggestion(
            operation=edit.operation,
            target_item_id=edit.target_item_id,
            current_text=current_text,
            suggested_text=text_result.suggested_text,
            evidence_ids=cited_ids,
            evidence_store=evidence_store,
            structured_resume=structured_resume,
        )
        evidence_sources = [
            item.label for eid in cited_ids if (item := evidence_store.get(eid)) is not None
        ]
        selected_by_default = (
            validation.status.value in _CLEANLY_SUPPORTED_STATUSES
            and text_result.confidence >= _SELECTED_BY_DEFAULT_CONFIDENCE_THRESHOLD
        )

        return TailoringSuggestion(
            suggestion_id=f"suggestion-{index}",
            target_section_id=edit.target_section_id,
            target_item_id=edit.target_item_id,
            operation=edit.operation,
            current_text=current_text,
            suggested_text=text_result.suggested_text,
            reason=edit.reason,
            evidence_ids=cited_ids,
            evidence_sources=evidence_sources,
            confidence=text_result.confidence,
            selected_by_default=selected_by_default,
            validation_status=validation.status,
            validation_issues=validation.issues,
        )
