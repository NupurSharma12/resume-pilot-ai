"""Domain models: the Resume Rewrite Engine's output (Stage 3) and Validation's output (Stage 4).

`TailoredSection` is the Rewrite Engine's raw, unvalidated output for one
`PlannedChange` — this is the exact type passed to
`LLMGateway.generate_structured` as `response_model` for Stage 3 (see
`ResumeRewritePromptBuilder`); every `TailoredBullet.supporting_evidence_ids`
claim on it is exactly that, a claim, until Stage 4 checks it against
what the Planner actually approved (see
`app.evidence.tailoring_validator.RewrittenChange`). `TailoredResume` is
what's left after Validation has rejected every bullet that doesn't
actually hold up — this, not a raw `TailoredSection`, is what a caller
should ever treat as "the tailored resume." Never confuse the two:
returning unvalidated sections directly to a caller would defeat the
entire point of Stage 4.
"""

from pydantic import BaseModel, ConfigDict, Field


class TailoredBullet(BaseModel):
    """One rewritten resume bullet, and the evidence it claims to be based on.

    `supporting_evidence_ids` is the Rewrite Engine's own citation of which
    `EvidenceStore` items justify this bullet's content — required, and
    required to be non-empty, for the same reason `PlannedChange.evidence_ids`
    is: a bullet with no cited evidence has nothing for Validation to check
    it against, so it can never pass (see `tailoring_validator`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(description="The rewritten bullet text.")
    supporting_evidence_ids: list[str] = Field(
        description="Evidence Store ids this bullet's content is claimed to be based on."
    )


class TailoredSection(BaseModel):
    """One resume section, rewritten to a list of bullets.

    Used two ways: as the Rewrite Engine's raw structured-output type for
    one `PlannedChange` (unvalidated — see this module's docstring), and
    as the building block of `TailoredResume` below (validated, after
    Stage 4 has filtered its bullets).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    heading: str = Field(description="The section heading, e.g. 'Summary', 'Experience'.")
    bullets: list[TailoredBullet] = Field(description="The section's rewritten bullets, in order.")


class TailoredResume(BaseModel):
    """A tailored resume after Validation: every remaining bullet has been checked and accepted.

    Built only from bullets that survived validation (see
    `tailoring_validator.validate_tailored_resume`). A section that has
    no accepted bullets left after validation is dropped entirely, rather
    than kept as an empty, misleading heading.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sections: list[TailoredSection] = Field(
        description="The validated, evidence-backed tailored resume, by section."
    )


class RejectedBullet(BaseModel):
    """One bullet Validation rejected, and why — never silently dropped without a reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: str = Field(description="The section heading the rejected bullet was under.")
    text: str = Field(description="The rejected bullet's text, exactly as proposed.")
    reason: str = Field(description="Why Validation rejected this bullet.")


class ValidationReport(BaseModel):
    """The full record of Stage 4's validation pass over every proposed bullet.

    Every bullet the Rewrite Engine proposed is accounted for here, one
    way or the other: it either contributed to `TailoredResume` (and is
    counted in `accepted_count`), or it's listed in `rejected_bullets`
    with a reason — there is no third, silent outcome.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_bullets: int = Field(description="Total bullets the Rewrite Engine proposed.")
    accepted_count: int = Field(description="Bullets that passed validation and were kept.")
    rejected_count: int = Field(description="Bullets that failed validation and were dropped.")
    rejected_bullets: list[RejectedBullet] = Field(
        description="Every rejected bullet and the reason it was rejected."
    )
    passed: bool = Field(
        description="True iff every proposed bullet was accepted (rejected_count == 0)."
    )
