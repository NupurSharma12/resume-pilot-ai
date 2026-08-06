"""Parses raw resume text into a `StructuredResume` of stable sections and items.

`ResumeStructureParser.parse` is a deterministic, heuristic, line-based
parser — not a real document layout engine. It has to work from plain
text alone (see `docs/features/interactive-tailored-resume.md` on why: no
original file bytes or formatting are retained anywhere in this
application by the time a resume reaches the Tailoring Engine), so it
cannot know anything a layout engine would (font weight, indentation
level, table structure). It infers section headings from a handful of
textual cues (short lines, no trailing sentence punctuation, ALL CAPS, or
a match against a list of common resume heading words -- deliberately
*not* ordinary Title Case, which a candidate's own name is
indistinguishable from) and infers items from blank-line/bullet-marker
boundaries within a section.

This is explicitly a best-effort heuristic, not a guarantee: an unusual
resume layout (headings that don't look like headings, a single
run-on paragraph with no bullets) will parse into fewer, coarser items
than a human would pick out by eye. That's an accepted limitation (see
this feature's docs), not silently hidden — every item this parser
produces is still real, verbatim text from the resume; it just might be
coarser-grained than ideal. Nothing here ever invents, drops, or
reorders resume content — every non-blank input line ends up in exactly
one output item.
"""

from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume

_BULLET_PREFIXES = "•-–—*◦▪"

_COMMON_HEADINGS = {
    "summary",
    "professional summary",
    "objective",
    "career objective",
    "experience",
    "work experience",
    "professional experience",
    "employment history",
    "skills",
    "technical skills",
    "core skills",
    "core competencies",
    "education",
    "projects",
    "certifications",
    "awards",
    "publications",
    "volunteer experience",
    "languages",
    "interests",
    "summary of qualifications",
}

_MAX_HEADING_LENGTH = 40
_MAX_HEADING_WORDS = 6


def _looks_like_heading(line: str) -> bool:
    """Decide whether `line` is likely a section heading, not resume content.

    Deliberately conservative: false negatives (a real heading missed,
    folded into the previous section's items) are far less harmful than
    false positives (an ordinary bullet or sentence mistaken for a
    heading, splitting a section in half) -- see this module's docstring.
    """
    stripped = line.strip().rstrip(":")
    if not stripped or len(stripped) > _MAX_HEADING_LENGTH:
        return False
    if stripped[0] in _BULLET_PREFIXES:
        return False
    if stripped.lower() in _COMMON_HEADINGS:
        return True
    if stripped.endswith((".", ",", ";")):
        return False
    words = stripped.split()
    if not words or len(words) > _MAX_HEADING_WORDS:
        return False
    # ALL CAPS is treated as a strong heading signal on its own. Ordinary
    # Title Case is deliberately *not* treated as a heading signal by
    # itself -- "Nupur Sharma" and "Core Skills" are structurally
    # indistinguishable by capitalization alone, and this codebase's own
    # extraction guidance in `docs/features/interactive-tailored-resume.md`
    # prefers a missed heading (folded into the previous section) over a
    # false one (splitting a name or a bullet in half). Only the common-
    # heading-word list above catches a heading that isn't ALL CAPS.
    return stripped.isupper()


def _split_items(raw_lines: list[str]) -> list[str]:
    """Group `raw_lines` (one section's content, before the next heading) into items.

    A line starting with a bullet marker becomes its own item. Runs of
    consecutive non-bullet, non-blank lines (e.g. a wrapped bullet with no
    marker on its continuation line, or a role/company/dates block) are
    joined into a single item; a blank line always starts a new item.
    """
    items: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = " ".join(part.strip() for part in buffer if part.strip())
        if text:
            items.append(text)
        buffer.clear()

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped[0] in _BULLET_PREFIXES:
            flush()
            content = stripped.lstrip(_BULLET_PREFIXES).strip()
            if content:
                items.append(content)
            continue
        buffer.append(stripped)
    flush()
    return items


class ResumeStructureParser:
    """Parses raw resume text into a `StructuredResume`.

    A plain class, not a `pydantic.BaseModel` — matching this codebase's
    established prompt-builder convention: it holds no state and
    validates nothing of its own.
    """

    def parse(self, resume_text: str) -> StructuredResume:
        """Split `resume_text` into stable, addressable sections and items.

        Content before the first detected heading (typically a name and
        contact details) becomes a section with an empty `heading` — kept
        rather than dropped, since every line of the original resume must
        end up somewhere (see this module's docstring); a heading-less
        block with no items is simply not emitted, so a resume with no
        content before its first heading doesn't produce a spurious empty
        section.
        """
        raw_sections: list[tuple[str, list[str]]] = []
        current_heading = ""
        current_lines: list[str] = []
        for line in resume_text.splitlines():
            if _looks_like_heading(line):
                raw_sections.append((current_heading, current_lines))
                current_heading = line.strip().rstrip(":")
                current_lines = []
            else:
                current_lines.append(line)
        raw_sections.append((current_heading, current_lines))

        sections: list[ResumeSection] = []
        for heading, lines in raw_sections:
            item_texts = _split_items(lines)
            if not heading and not item_texts:
                continue
            section_id = f"section-{len(sections)}"
            items = [
                ResumeItem(item_id=f"{section_id}-item-{index}", text=text)
                for index, text in enumerate(item_texts)
            ]
            sections.append(ResumeSection(section_id=section_id, heading=heading, items=items))

        return StructuredResume(sections=sections)
