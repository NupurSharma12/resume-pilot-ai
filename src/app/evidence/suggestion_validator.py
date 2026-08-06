"""Validates one `TailoringSuggestion`'s text against its cited evidence and structure.

Used twice: once per suggestion at generation time (Stage 4, populating
`TailoringSuggestion.validation_status`/`.validation_issues` so the
review UI can show it before the user even decides), and again at apply
time for any suggestion whose text the user edited (see
`app.tailoring.applier`) — edited text is never trusted just because the
original suggestion was already validated; it's revalidated from
scratch, since the user could have typed anything.

Pure Python, not another LLM call — trusting a model to grade its own (or
another model's) work would reintroduce exactly the hallucination risk
this stage exists to catch. Mirrors the original Tailoring Engine's
`tailoring_validator.py` claim-detection heuristic (now superseded, see
`docs/features/tailoring-engine.md`) almost exactly — the heuristic
itself didn't need to change, only what it's applied to (one suggestion's
text instead of one whole rewritten section).
"""

import re
from dataclasses import dataclass, field

from app.models.evidence_store import EvidenceSource, EvidenceStore
from app.models.resume_structure import StructuredResume
from app.models.tailoring_suggestions import (
    REPLACEMENT_OPERATIONS,
    SuggestionOperation,
    SuggestionValidationStatus,
)

# Common resume-bullet vocabulary (action verbs, articles, prepositions)
# that gets capitalized at a sentence's start or is otherwise unremarkable
# — excluded so the claim-term heuristic below doesn't flag "Led" or "The"
# as an unsupported technology claim just because it's capitalized.
_SKIP_WORDS = {
    "led", "built", "developed", "designed", "implemented", "managed", "created",
    "improved", "reduced", "increased", "delivered", "architected", "collaborated",
    "drove", "owned", "spearheaded", "launched", "established", "optimized",
    "mentored", "conducted", "coordinated", "authored", "maintained", "supported",
    "the", "a", "an", "this", "that", "these", "those", "and", "or", "for", "with",
    "to", "of", "in", "on", "at", "by", "as", "from", "was", "were", "is", "are",
    "i", "my", "our", "team", "teams", "project", "projects", "work", "across",
}  # fmt: skip

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.%-]*")


def _claim_terms(text: str) -> set[str]:
    """Extract words from `text` that look like a specific, checkable claim.

    A deliberately conservative, best-effort heuristic — not real NLP or
    named-entity recognition. A word is treated as a "claim" if it's an
    ALL-CAPS acronym, contains a digit, or is capitalized outside
    `_SKIP_WORDS`. The text's very first word is never treated as a claim
    (resume bullets conventionally open with a past-tense action verb —
    see the original Tailoring Engine's identical heuristic for the full
    reasoning, unchanged here).
    """
    terms = set()
    for position, match in enumerate(_WORD_RE.finditer(text)):
        if position == 0:
            continue
        word = match.group(0).strip(".")
        if len(word) < 2:
            continue
        if word.lower() in _SKIP_WORDS:
            continue
        if word.isupper() or any(char.isdigit() for char in word) or word[0].isupper():
            terms.add(word)
    return terms


def _find_unsupported_claims(text: str, cited_evidence_text: str) -> list[str]:
    """Return every claim term in `text` that doesn't appear in `cited_evidence_text`."""
    cited_lower = cited_evidence_text.lower()
    return sorted(term for term in _claim_terms(text) if term.lower() not in cited_lower)


@dataclass(frozen=True)
class SuggestionValidationResult:
    status: SuggestionValidationStatus
    issues: list[str] = field(default_factory=list)


def _evidence_provenance(
    evidence_ids: list[str], evidence_store: EvidenceStore
) -> set[EvidenceSource]:
    sources = set()
    for evidence_id in evidence_ids:
        item = evidence_store.get(evidence_id)
        if item is not None:
            sources.add(item.source)
    return sources


def validate_suggestion(
    *,
    operation: SuggestionOperation,
    target_item_id: str,
    current_text: str | None,
    suggested_text: str,
    evidence_ids: list[str],
    evidence_store: EvidenceStore,
    structured_resume: StructuredResume,
) -> SuggestionValidationResult:
    """Validate one suggestion's structure and evidentiary support.

    Checked in order, first failure wins (matches the original
    validator's "reject on the first thing that fails" shape):

    1. Structural: the target item exists; `append` actually extends
       (rather than discards) the original text; a true-replacement
       operation (see `REPLACEMENT_OPERATIONS`) has non-empty
       `current_text`, an insertion has none.
    2. Evidence exists: every cited id is real.
    3. Evidence supports the text: no claim-like term in `suggested_text`
       is absent from the cited evidence's own text.

    A suggestion that passes is classified by *where* its evidence came
    from — resume-only, conversation-only, or both — never penalized for
    resting entirely on the original resume (see
    `SuggestionValidationStatus`'s docstring): an unchanged, already-true
    statement doesn't need a Career Conversation turn to back it up.
    """
    if structured_resume.get_item(target_item_id) is None:
        return SuggestionValidationResult(
            SuggestionValidationStatus.STRUCTURALLY_INVALID,
            [f"Target item '{target_item_id}' does not exist in the resume."],
        )

    is_replacement = operation in REPLACEMENT_OPERATIONS
    if is_replacement and not current_text:
        return SuggestionValidationResult(
            SuggestionValidationStatus.STRUCTURALLY_INVALID,
            [
                f"Operation '{operation.value}' requires the item's current text, "
                "but none was given."
            ],
        )
    if not is_replacement and current_text:
        return SuggestionValidationResult(
            SuggestionValidationStatus.STRUCTURALLY_INVALID,
            [f"Operation '{operation.value}' inserts a new item and must not carry current_text."],
        )

    if operation == SuggestionOperation.REMOVE:
        # Nothing further to validate -- removing a real item can't
        # fabricate anything, and an empty `suggested_text` is expected.
        provenance = _evidence_provenance(evidence_ids, evidence_store)
        return SuggestionValidationResult(_status_for_provenance(provenance))

    if operation == SuggestionOperation.APPEND:
        assert current_text is not None  # guaranteed by the is_replacement check above
        if current_text.strip() not in suggested_text:
            return SuggestionValidationResult(
                SuggestionValidationStatus.STRUCTURALLY_INVALID,
                ["'append' must keep the item's existing text intact and add to it."],
            )

    if not evidence_ids:
        return SuggestionValidationResult(
            SuggestionValidationStatus.UNSUPPORTED, ["No supporting evidence cited."]
        )

    unknown_ids = evidence_store.unknown_ids(evidence_ids)
    if unknown_ids:
        return SuggestionValidationResult(
            SuggestionValidationStatus.UNSUPPORTED,
            [f"Cites unknown evidence id(s): {', '.join(unknown_ids)}."],
        )

    cited_text = evidence_store.text_for_ids(evidence_ids)
    unsupported_terms = _find_unsupported_claims(suggested_text, cited_text)
    if unsupported_terms:
        return SuggestionValidationResult(
            SuggestionValidationStatus.UNSUPPORTED,
            [f"Contains term(s) not present in cited evidence: {', '.join(unsupported_terms)}."],
        )

    provenance = _evidence_provenance(evidence_ids, evidence_store)
    return SuggestionValidationResult(_status_for_provenance(provenance))


def _status_for_provenance(sources: set[EvidenceSource]) -> SuggestionValidationStatus:
    has_resume = EvidenceSource.RESUME in sources or EvidenceSource.RESUME_ANALYSIS in sources
    has_conversation = EvidenceSource.CONVERSATION in sources
    if has_resume and has_conversation:
        return SuggestionValidationStatus.SUPPORTED_BY_BOTH
    if has_conversation:
        return SuggestionValidationStatus.SUPPORTED_BY_CONVERSATION
    return SuggestionValidationStatus.SUPPORTED_BY_ORIGINAL_RESUME
