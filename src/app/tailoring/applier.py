"""Deterministically applies a user's selected suggestions to produce a final resume.

`SuggestionApplier` is the only place approved edits actually touch resume
content. It makes no LLM calls of its own — every suggestion's text was
already produced and validated at generation time (see
`TailoringSuggestionWorkflow`); this module's job is purely mechanical:
verify the client's selections are legitimate, apply exactly the selected
operations and nothing else, and leave everything unaffected byte-for-byte
untouched. There is deliberately no "rewrite the whole resume" step here —
see `docs/features/interactive-tailored-resume.md` for why a second
unrestricted LLM call after approval would defeat the entire point of the
review step.

## Trust boundary

`apply` never trusts suggestion *content* supplied by the client — only
`suggestion_id`s (which operation to run) and, optionally, edited
`suggested_text` (which is revalidated, never taken on faith). Every
selected id is checked against the `StoredPlan` this backend actually
generated (see `TailoringPlanStore`); an id that doesn't belong to the
plan is rejected outright, not silently ignored.

## Conflict policy

Two selected suggestions conflict if they would both try to determine the
same physical outcome at the same anchor: either two suggestions both
mutate the same target item's own content (any of `REPLACEMENT_OPERATIONS`
— there is no principled way to apply two independent rewrites of one
line), or two suggestions both insert a new item at the same position
relative to the same anchor (two `insert_before` on the same item, or two
`insert_after` on the same item — there is no defined order between them).
An `insert_before`/`insert_after` does *not* conflict with a mutation of
its own anchor item (e.g. inserting a new bullet after item X while also
appending a phrase to item X's own text) — those are independent edits at
different physical positions. Any conflict is rejected outright (see
`SuggestionConflictError`); this module never guesses which one the user
"really" meant.

## Deterministic order

Suggestions are applied by walking the resume in its own original
section/item order — never in selection order, submission order, or
confidence order — so the result never depends on incidental ordering in
the request.
"""

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.evidence.suggestion_validator import validate_suggestion
from app.models.evidence_store import EvidenceStore
from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume
from app.models.tailoring_suggestions import (
    REPLACEMENT_OPERATIONS,
    SuggestionOperation,
    SuggestionPlan,
    SuggestionValidationStatus,
    TailoringSuggestion,
)

logger = get_logger(__name__)

_ACCEPTABLE_FINAL_STATUSES = frozenset(
    {
        SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME,
        SuggestionValidationStatus.SUPPORTED_BY_CONVERSATION,
        SuggestionValidationStatus.SUPPORTED_BY_BOTH,
    }
)


class UnknownSuggestionIdError(RuntimeError):
    """Raised when a selected (or edited) suggestion id doesn't belong to the generated plan."""


class SuggestionConflictError(RuntimeError):
    """Raised when two or more selected suggestions collide at the same anchor.

    Carries `target_item_id` and `suggestion_ids` so the API layer can
    report exactly which suggestions the user needs to choose between,
    rather than a generic failure.
    """

    def __init__(self, target_item_id: str, suggestion_ids: list[str]) -> None:
        super().__init__(
            f"Suggestions {', '.join(suggestion_ids)} conflict at item {target_item_id!r}; "
            "select only one of them."
        )
        self.target_item_id = target_item_id
        self.suggestion_ids = suggestion_ids


class SuggestionRevalidationFailedError(RuntimeError):
    """Raised when a user-edited suggestion's text no longer holds up under validation.

    The original (model-generated) text for this suggestion may still be
    valid — this only means the *edited* version isn't. The caller should
    surface `issues` to the user and leave the prior successful result in
    place, never apply the failing edit.
    """

    def __init__(self, suggestion_id: str, issues: list[str]) -> None:
        super().__init__(
            f"Edited text for suggestion {suggestion_id!r} failed validation: {'; '.join(issues)}"
        )
        self.suggestion_id = suggestion_id
        self.issues = issues


@dataclass(frozen=True)
class FinalValidationReport:
    """A summary check over the assembled final resume, after all edits are applied."""

    is_valid: bool
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApplyResult:
    """The outcome of one `SuggestionApplier.apply` call."""

    final_resume: StructuredResume
    applied_suggestion_ids: list[str]
    final_validation: FinalValidationReport


class SuggestionApplier:
    """Applies a caller-selected subset of a `StoredPlan`'s suggestions to its resume."""

    def apply(
        self,
        stored_structured_resume: StructuredResume,
        plan: SuggestionPlan,
        evidence_store: EvidenceStore,
        selected_suggestion_ids: list[str],
        edited_texts: dict[str, str],
    ) -> ApplyResult:
        """Apply the selected suggestions (with any edits revalidated) and return the result.

        `stored_structured_resume`/`plan`/`evidence_store` must be the
        exact triple returned together by generation (see
        `TailoringPlanStore.StoredPlan`) — this method re-anchors every
        suggestion against `stored_structured_resume`, never a freshly
        re-parsed one, so ids can never drift from what was actually
        planned against.
        """
        logger.info(
            "suggestion_apply_started",
            plan_id=plan.plan_id,
            selected_count=len(selected_suggestion_ids),
            edited_count=len(edited_texts),
        )

        suggestions_by_id = {s.suggestion_id: s for s in plan.suggestions}
        selected = self._resolve_selected(selected_suggestion_ids, edited_texts, suggestions_by_id)
        selected = self._apply_edits(
            selected, edited_texts, evidence_store, stored_structured_resume
        )
        self._check_conflicts(selected)

        final_resume = self._build_final_resume(stored_structured_resume, selected)
        final_validation = self._run_final_validation(
            stored_structured_resume, final_resume, selected
        )

        logger.info(
            "suggestion_apply_completed",
            plan_id=plan.plan_id,
            applied_count=len(selected),
            final_valid=final_validation.is_valid,
        )
        return ApplyResult(
            final_resume=final_resume,
            applied_suggestion_ids=[s.suggestion_id for s in selected],
            final_validation=final_validation,
        )

    @staticmethod
    def _resolve_selected(
        selected_suggestion_ids: list[str],
        edited_texts: dict[str, str],
        suggestions_by_id: dict[str, TailoringSuggestion],
    ) -> list[TailoringSuggestion]:
        unknown = [sid for sid in selected_suggestion_ids if sid not in suggestions_by_id]
        unknown += [sid for sid in edited_texts if sid not in suggestions_by_id]
        if unknown:
            raise UnknownSuggestionIdError(
                f"Suggestion id(s) not found in this plan: {', '.join(sorted(set(unknown)))}"
            )
        return [suggestions_by_id[sid] for sid in selected_suggestion_ids]

    @staticmethod
    def _apply_edits(
        selected: list[TailoringSuggestion],
        edited_texts: dict[str, str],
        evidence_store: EvidenceStore,
        structured_resume: StructuredResume,
    ) -> list[TailoringSuggestion]:
        """Substitute any user-edited text and revalidate it before it can be applied.

        A suggestion's original, model-generated text was already
        validated at generation time — only text the *user* changed needs
        re-checking here.
        """
        result = []
        for suggestion in selected:
            if suggestion.suggestion_id not in edited_texts:
                result.append(suggestion)
                continue

            edited_text = edited_texts[suggestion.suggestion_id]
            validation = validate_suggestion(
                operation=suggestion.operation,
                target_item_id=suggestion.target_item_id,
                current_text=suggestion.current_text,
                suggested_text=edited_text,
                evidence_ids=suggestion.evidence_ids,
                evidence_store=evidence_store,
                structured_resume=structured_resume,
            )
            if validation.status not in _ACCEPTABLE_FINAL_STATUSES:
                raise SuggestionRevalidationFailedError(suggestion.suggestion_id, validation.issues)

            result.append(
                suggestion.model_copy(
                    update={
                        "suggested_text": edited_text,
                        "validation_status": validation.status,
                        "validation_issues": validation.issues,
                    }
                )
            )
        return result

    @staticmethod
    def _check_conflicts(selected: list[TailoringSuggestion]) -> None:
        groups: dict[tuple[str, str], list[TailoringSuggestion]] = {}
        for suggestion in selected:
            category = (
                "mutate"
                if suggestion.operation in REPLACEMENT_OPERATIONS
                else suggestion.operation.value
            )
            groups.setdefault((suggestion.target_item_id, category), []).append(suggestion)

        for (target_item_id, _category), group in groups.items():
            if len(group) > 1:
                raise SuggestionConflictError(target_item_id, [s.suggestion_id for s in group])

    @staticmethod
    def _build_final_resume(
        structured_resume: StructuredResume, selected: list[TailoringSuggestion]
    ) -> StructuredResume:
        by_target_item: dict[str, list[TailoringSuggestion]] = {}
        for suggestion in selected:
            by_target_item.setdefault(suggestion.target_item_id, []).append(suggestion)

        sections = [
            SuggestionApplier._apply_to_section(section, by_target_item)
            for section in structured_resume.sections
        ]
        return StructuredResume(sections=sections)

    @staticmethod
    def _apply_to_section(
        section: ResumeSection, by_target_item: dict[str, list[TailoringSuggestion]]
    ) -> ResumeSection:
        new_items: list[ResumeItem] = []
        for item in section.items:
            targeting = by_target_item.get(item.item_id, [])

            for suggestion in targeting:
                if suggestion.operation == SuggestionOperation.INSERT_BEFORE:
                    new_items.append(
                        ResumeItem(
                            item_id=f"{suggestion.suggestion_id}-new",
                            text=suggestion.suggested_text,
                        )
                    )

            mutation = next((s for s in targeting if s.operation in REPLACEMENT_OPERATIONS), None)
            if mutation is None:
                new_items.append(item)
            elif mutation.operation != SuggestionOperation.REMOVE:
                new_items.append(ResumeItem(item_id=item.item_id, text=mutation.suggested_text))
            # REMOVE: the item is dropped -- nothing appended.

            for suggestion in targeting:
                if suggestion.operation == SuggestionOperation.INSERT_AFTER:
                    new_items.append(
                        ResumeItem(
                            item_id=f"{suggestion.suggestion_id}-new",
                            text=suggestion.suggested_text,
                        )
                    )

        return ResumeSection(
            section_id=section.section_id, heading=section.heading, items=new_items
        )

    @staticmethod
    def _run_final_validation(
        original_resume: StructuredResume,
        final_resume: StructuredResume,
        selected: list[TailoringSuggestion],
    ) -> FinalValidationReport:
        """Check invariants that only make sense once the whole resume is assembled.

        Per-suggestion evidence/claim validation already happened at
        generation time (and again for any edited text, in
        `_apply_edits`) — this final pass only checks properties of the
        *assembled result*: that no unapproved item changed, and that no
        duplicate bullet text was introduced within a section.
        """
        messages: list[str] = []
        touched_item_ids = {s.target_item_id for s in selected}

        original_by_id = {
            item.item_id: item.text
            for section in original_resume.sections
            for item in section.items
        }
        final_by_id = {
            item.item_id: item.text for section in final_resume.sections for item in section.items
        }
        for item_id, original_text in original_by_id.items():
            if item_id in touched_item_ids:
                continue
            if final_by_id.get(item_id) != original_text:
                messages.append(f"Unapproved change detected on untouched item {item_id!r}.")

        for section in final_resume.sections:
            seen: dict[str, str] = {}
            for item in section.items:
                key = item.text.strip().lower()
                if not key:
                    continue
                if key in seen:
                    messages.append(
                        f"Duplicate bullet introduced in section {section.section_id!r}: "
                        f"{item.text!r}"
                    )
                seen[key] = item.item_id

        return FinalValidationReport(is_valid=not messages, messages=messages)
