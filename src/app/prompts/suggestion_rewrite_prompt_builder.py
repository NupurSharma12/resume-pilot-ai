"""Production prompt builder: assembles an `LLMRequest` for one suggestion's rewrite (Stage 3).

`SuggestionRewritePromptBuilder` owns the prompt engineering for turning
one `SuggestedEdit` (Stage 2's targeted, textless proposal) into actual
text — the one stage in this pipeline allowed to write prose, and only
within the hard constraints below. It performs no planning of its own
(what to change, and which item, was already decided) and no validation
of its own (whether the result actually holds up is
`app.evidence.suggestion_validator`'s job, not this prompt's to get right
by construction) — it only assembles the request.

One call per `SuggestedEdit`, never a batch — mirrors the superseded
`ResumeRewritePromptBuilder`'s per-change calls exactly (see
`docs/features/tailoring-engine.md`), and for the same reason: the
Planner is this pipeline's single evidence authority, and each call is
scoped to only the evidence *that specific edit* was approved to use, via
`evidence_store.catalog_text_for_ids(edit.evidence_ids)` — never the full
catalog. The Rewrite Engine executes, it doesn't decide.
"""

from app.gateways.llm.models import LLMRequest
from app.models.evidence_store import EvidenceStore
from app.models.tailoring_suggestions import SuggestedEdit

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.3

_SYSTEM_PROMPT = """\
You are an experienced resume editor executing one specific, pre-approved \
edit to one specific line of a candidate's resume. You are not an AI \
resume writer inventing an ideal candidate — you are improving the \
presentation of a real person's real, already-established experience, \
and you are making exactly the one change described below, nothing else.

## You have been given a restricted evidence catalog

The Evidence Catalog below is NOT the candidate's full evidence store — \
it is only the evidence approved for this one specific edit. You must \
never cite, in `evidence_ids`, any id that is not listed in this \
catalog. If a strong version of this edit would benefit from a fact \
that isn't in this catalog, you do not have access to it — write a more \
modest, fully-supported version instead. Do not invent an id, and do \
not guess that a fact might exist elsewhere.

## Absolute rules — never violate these

- Never invent experience, employers, job titles, dates, technologies, \
responsibilities, achievements, or metrics that are not present in the \
Evidence Catalog below.
- Never exaggerate scope, seniority, or impact beyond what the evidence \
actually supports.
- Never fabricate a number, percentage, or other metric.
- Never add a technology, tool, or skill that is not named in the \
Evidence Catalog.

## Follow the exact operation you were given

- `append`: your `suggested_text` must be the item's FULL resulting \
text — the original text, unchanged, followed by the addition. Do not \
drop, reorder, or reword the original part.
- `update` / `replace`: your `suggested_text` is the full resulting \
text for this item, revised as the reason describes.
- `add_emphasis`: reorder or reword the item's existing wording to lead \
with what matters most for this job — introduce no new claim.
- `remove`: `suggested_text` should be an empty string.
- `insert_before` / `insert_after`: `suggested_text` is the full text of \
a brand-new item, grounded entirely in the evidence catalog below.

## Cite your evidence

`evidence_ids` must list which of the offered evidence ids your text is \
actually based on — you do not have to use all of it, but you may never \
add an id that wasn't offered. A downstream validation step will check \
that every claim-like detail in your text actually appears in the \
evidence you cited for it, and will discard this suggestion entirely if \
it doesn't hold up — so if you cannot ground the edit in real, cited \
evidence, keep the change as minimal as the evidence allows rather than \
guessing.

## Report your confidence honestly

Report your own genuine confidence (0-100) that this text is fully \
evidence-backed and follows the operation exactly. Do not inflate it to \
make the edit look more certain than it is — a downstream step uses this \
to decide whether the suggestion should start pre-selected for the \
candidate.\
"""


class SuggestionRewritePromptBuilder:
    """Builds an `LLMRequest` for Stage 3 (one suggestion's rewrite) from the edit and its evidence.

    A plain class, not a `pydantic.BaseModel`, matching this codebase's
    established prompt-builder pattern.
    """

    def build(
        self,
        edit: SuggestedEdit,
        current_text: str | None,
        evidence_store: EvidenceStore,
        custom_instructions: str | None,
    ) -> LLMRequest:
        """Embed the operation, the target item's current text (if any), and its approved evidence.

        `current_text` is passed explicitly (not re-derived from
        `edit.target_item_id` here) so the caller — which already looked
        it up to decide whether this edit is a replacement or an
        insertion — stays the single source of truth for that lookup.
        """
        user_prompt = (
            f"Operation: {edit.operation.value}\n"
            f"Reason: {edit.reason}\n"
            f"Current text of the target item"
            f"{' (there is none -- you are inserting a new item)' if current_text is None else ''}"
            f":\n{current_text or '(none)'}\n\n"
            f"Evidence Catalog (the ONLY evidence you may cite for this edit):\n"
            f"{evidence_store.catalog_text_for_ids(edit.evidence_ids)}\n\n"
            f"Candidate's custom instructions (constraints only, never evidence):\n"
            f"{custom_instructions or 'None provided.'}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )
