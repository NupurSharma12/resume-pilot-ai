"""Domain model: a resume broken into stable, addressable sections and items.

`StructuredResume` is what makes per-bullet suggestions possible at all.
Everything upstream of this feature (`ResumeAnalysisResult`, the Career
Conversation transcript, the original Tailoring Engine) only ever dealt
with the resume as one opaque string — enough to *analyze* it, but not
enough to say "append two words to bullet 3 of Experience" or "this
suggestion targets exactly this item and no other." `ResumeSection`/
`ResumeItem` give every line of the resume a stable id
(`section_id`/`item_id`) that a `TailoringSuggestion` can target, that
`EvidenceStore` can cite, and that `SuggestionApplier` can mutate
precisely — see `app.resume_structure.parser` for how this is built from
raw text, and `app.tailoring.applier` for how it's mutated.
"""

from pydantic import BaseModel, ConfigDict, Field


class ResumeItem(BaseModel):
    """One addressable line/bullet within a resume section.

    `item_id` is stable for as long as `resume_text` doesn't change (the
    parser is a pure function of the text — see
    `ResumeStructureParser.parse`), which is what lets a suggestion
    generated in one request still resolve correctly when applied in a
    later request, without the backend needing to persist the resume's
    parsed structure in between (see `TailoringPlanStore`'s docstring).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str = Field(description="Stable identifier, e.g. 'section-1-item-2'.")
    text: str = Field(description="The item's text, exactly as it appears in the resume.")


class ResumeSection(BaseModel):
    """One heading and the items under it, in original order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str = Field(description="Stable identifier, e.g. 'section-1'.")
    heading: str = Field(description="The section heading as it appears in the resume.")
    items: list[ResumeItem] = Field(description="The section's items, in original order.")


class StructuredResume(BaseModel):
    """A full resume broken into stable, addressable sections and items."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sections: list[ResumeSection] = Field(description="The resume's sections, in original order.")

    def get_item(self, item_id: str) -> ResumeItem | None:
        """Look up one item by id, or `None` if it doesn't exist in this resume."""
        for section in self.sections:
            for item in section.items:
                if item.item_id == item_id:
                    return item
        return None

    def get_section(self, section_id: str) -> ResumeSection | None:
        """Look up one section by id, or `None` if it doesn't exist in this resume."""
        for section in self.sections:
            if section.section_id == section_id:
                return section
        return None

    def to_text(self) -> str:
        """Render back to plain text, heading-then-items, one item per line.

        Not guaranteed to be byte-identical to the original text it was
        parsed from (whitespace/blank-line differences are not
        preserved) — this is a *content*-faithful re-rendering, which is
        exactly what every export format is built from, not a byte-exact
        round trip.
        """
        lines: list[str] = []
        for section in self.sections:
            if section.heading:
                lines.append(section.heading)
            for item in section.items:
                lines.append(item.text)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
