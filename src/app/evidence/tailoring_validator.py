"""Stage 4 of the Tailoring Engine: Validation.

`validate_tailored_resume` is pure Python, not another LLM call — trusting
a model to grade its own (or another model's) work would reintroduce
exactly the hallucination risk this stage exists to catch. For every
bullet the Resume Rewrite Engine proposed, this checks three things, in
order, and rejects on the first one that fails:

1. The bullet cites at least one evidence id at all.
2. Every id it cites was actually approved by the Planner *for the
   specific change that produced this bullet* — not merely a real id
   somewhere in the `EvidenceStore`. The Planner is this pipeline's
   single authority on what evidence may be used (see
   `TailoringPlannerPromptBuilder`); the Rewrite Engine executes, it
   doesn't decide, and this check is what makes that a validated
   guarantee rather than only a prompt instruction. See `RewrittenChange`
   below for how a bullet gets tied back to the change that authorized it.
3. The bullet doesn't contain a claim-like term (a technology, tool, or
   other proper-noun-style detail) that doesn't appear anywhere in the
   text of the evidence it cited.

A bullet that survives all three is accepted into the final
`TailoredResume`; anything else is dropped and recorded in the
`ValidationReport` with a specific reason — never silently kept, per the
pipeline's explicit requirement.
"""

import re
from dataclasses import dataclass

from app.models.evidence_store import EvidenceStore
from app.models.tailored_resume import (
    RejectedBullet,
    TailoredResume,
    TailoredSection,
    ValidationReport,
)
from app.models.tailoring_plan import PlannedChange

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


@dataclass(frozen=True)
class RewrittenChange:
    """One `PlannedChange`, paired with what the Rewrite Engine actually produced for it.

    This pairing is what lets Stage 4 check a bullet's cited evidence
    against exactly what the Planner approved *for the change that
    produced it* — not against the whole `EvidenceStore`, and not against
    some other change's approved evidence. `TailoringWorkflow._generate_rewrite`
    builds one of these per `generate_structured` call: one call per
    planned change, each scoped (via `ResumeRewritePromptBuilder`) to only
    that change's approved evidence ids.
    """

    change: PlannedChange
    section: TailoredSection


def _claim_terms(text: str) -> set[str]:
    """Extract words from `text` that look like a specific, checkable claim.

    A deliberately conservative, best-effort heuristic — not real NLP or
    named-entity recognition — since precision isn't the point here, safety
    is: a word is treated as a "claim" if it's an ALL-CAPS acronym, contains
    a digit (a version, a percentage, a year), or is capitalized outside
    `_SKIP_WORDS`. This over-flags some ordinary capitalized words as
    needing evidence rather than under-flag a real hallucination; a
    rejected-but-actually-fine bullet is a far cheaper mistake for this
    engine to make than an accepted fabrication.

    The bullet's very first word is never treated as a claim, regardless
    of what it is: resume bullets conventionally open with a past-tense
    action verb ("Containerized...", "Orchestrated...", "Mentored..."),
    which is a style choice, not a fact needing its own citation — and
    matching every possible verb by an exhaustive list is both fragile and
    prone to exactly the kind of tense mismatch ("Containerized" the
    bullet says vs. "containerize" the evidence says) that would make this
    heuristic reject well-supported bullets for the wrong reason.
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


def _find_unsupported_claims(bullet_text: str, cited_evidence_text: str) -> list[str]:
    """Return every claim term in `bullet_text` that doesn't appear in `cited_evidence_text`.

    Case-insensitive substring match against the cited evidence's text
    only — not the whole Evidence Store — so a bullet must be supported by
    the *specific* evidence it claims to cite, not by something true
    somewhere else in the candidate's history that this bullet never
    referenced.
    """
    cited_lower = cited_evidence_text.lower()
    return sorted(term for term in _claim_terms(bullet_text) if term.lower() not in cited_lower)


def validate_tailored_resume(
    rewritten_changes: list[RewrittenChange], evidence_store: EvidenceStore
) -> tuple[TailoredResume, ValidationReport]:
    """Validate every bullet against the change that produced it, and return the accepted result.

    Two or more `PlannedChange`s can legitimately target the same
    section heading (e.g. one "rewrite" and one later "add_emphasis"
    change, both for "Summary") — their accepted bullets are merged under
    one `TailoredSection` per distinct heading in the final
    `TailoredResume`, in the order headings were first seen. A heading
    that ends up with zero accepted bullets across every change that
    touched it is dropped entirely, rather than kept as an empty,
    misleading heading.
    """
    accepted_bullets_by_heading: dict[str, list] = {}
    heading_order: list[str] = []
    rejected_bullets: list[RejectedBullet] = []
    total_bullets = 0

    for rewritten in rewritten_changes:
        approved_ids = set(rewritten.change.evidence_ids)
        heading = rewritten.section.heading

        for bullet in rewritten.section.bullets:
            total_bullets += 1

            if not bullet.supporting_evidence_ids:
                rejected_bullets.append(
                    RejectedBullet(
                        section=heading,
                        text=bullet.text,
                        reason="No supporting evidence cited.",
                    )
                )
                continue

            unapproved_ids = [
                evidence_id
                for evidence_id in bullet.supporting_evidence_ids
                if evidence_id not in approved_ids
            ]
            if unapproved_ids:
                rejected_bullets.append(
                    RejectedBullet(
                        section=heading,
                        text=bullet.text,
                        reason=(
                            "Cites evidence id(s) the tailoring plan did not approve for "
                            f"this change: {', '.join(unapproved_ids)}."
                        ),
                    )
                )
                continue

            cited_text = evidence_store.text_for_ids(bullet.supporting_evidence_ids)
            unsupported_terms = _find_unsupported_claims(bullet.text, cited_text)
            if unsupported_terms:
                rejected_bullets.append(
                    RejectedBullet(
                        section=heading,
                        text=bullet.text,
                        reason=(
                            "Contains term(s) not present in cited evidence: "
                            f"{', '.join(unsupported_terms)}."
                        ),
                    )
                )
                continue

            if heading not in accepted_bullets_by_heading:
                accepted_bullets_by_heading[heading] = []
                heading_order.append(heading)
            accepted_bullets_by_heading[heading].append(bullet)

    accepted_sections = [
        TailoredSection(heading=heading, bullets=accepted_bullets_by_heading[heading])
        for heading in heading_order
    ]

    report = ValidationReport(
        total_bullets=total_bullets,
        accepted_count=total_bullets - len(rejected_bullets),
        rejected_count=len(rejected_bullets),
        rejected_bullets=rejected_bullets,
        passed=len(rejected_bullets) == 0,
    )
    return TailoredResume(sections=accepted_sections), report
