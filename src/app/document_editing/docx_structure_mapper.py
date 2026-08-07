"""Maps a real, opened DOCX `Document` directly to a `StructuredResume` + editable nodes.

`DocxStructureMapper` is the DOCX-specific twin of
`app.resume_structure.parser.ResumeStructureParser`, and deliberately
reuses that module's heading/bullet heuristics (`looks_like_heading`,
`BULLET_PREFIXES`) rather than inventing a second set that could drift —
but it does not reuse the text-splitting logic itself, because it doesn't
need to: a real DOCX paragraph is already exactly one logical unit (Word
wraps text visually, it never splits one bullet across two `<w:p>`
elements), so there is no "join consecutive lines" step to replicate.
Every non-blank paragraph maps to exactly one `ResumeItem`.

This is also the reason `StructuredResume`s built by this mapper can be
*more* accurately segmented than ones built from plain extracted text by
`ResumeStructureParser` -- paragraph boundaries come from the document
itself, not from re-inferring them out of a flattened string.

The two outputs -- a `StructuredResume` (immutable data, for the existing
Planner/Rewrite/Validate pipeline, entirely unchanged) and a
`dict[item_id, DocxParagraphNode]` (live, mutable handles into the same
open `Document`, for `DocxDocumentEditor`) -- share the exact same
`item_id`/`section_id` values by construction: both are produced from the
same single walk over the same paragraphs, so there is no separate
alignment step that could disagree with itself.
"""

from docx.document import Document as DocumentObject
from docx.text.paragraph import Paragraph

from app.document_editing.docx_nodes import DocxParagraphNode
from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume
from app.resume_structure.parser import BULLET_PREFIXES, looks_like_heading


def _strip_bullet_prefix(text: str) -> str:
    """Strip a literal, typed bullet character, if the paragraph text starts with one.

    Word's own list/numbering formatting (`numPr`) never appears in
    `paragraph.text` at all -- it's rendered, not typed -- so this only
    ever fires for a resume that used literal bullet characters instead
    of Word's list feature. Purely a display-text cleanup: the
    `DocxParagraphNode` this item pairs with still wraps the paragraph's
    real, unmodified text and formatting.
    """
    stripped = text.strip()
    if stripped and stripped[0] in BULLET_PREFIXES:
        return stripped.lstrip(BULLET_PREFIXES).strip()
    return stripped


class DocxStructureMapper:
    """Builds a `StructuredResume` and its paragraph-node map from an open DOCX `Document`."""

    def map(
        self, document: DocumentObject
    ) -> tuple[StructuredResume, dict[str, DocxParagraphNode]]:
        """Walk `document`'s body paragraphs once, producing both outputs together.

        Only top-level body paragraphs are considered -- table cells,
        headers, and footers are out of scope for *mapping* in this
        version (matching `app.ingestion.extractor.DocxDocumentExtractor`'s
        existing, documented scope limit), which is exactly why editing
        never touches them: nothing outside this walk is ever mutated, so
        headers/footers/tables are preserved by construction, not edited.
        """
        raw_sections: list[tuple[str, list[Paragraph]]] = []
        current_heading = ""
        current_paragraphs: list[Paragraph] = []
        for paragraph in document.paragraphs:
            if looks_like_heading(paragraph.text):
                raw_sections.append((current_heading, current_paragraphs))
                current_heading = paragraph.text.strip().rstrip(":")
                current_paragraphs = []
            else:
                current_paragraphs.append(paragraph)
        raw_sections.append((current_heading, current_paragraphs))

        sections: list[ResumeSection] = []
        nodes: dict[str, DocxParagraphNode] = {}
        for heading, paragraphs in raw_sections:
            item_paragraphs = [p for p in paragraphs if p.text.strip()]
            if not heading and not item_paragraphs:
                continue
            section_id = f"section-{len(sections)}"
            items = []
            for index, paragraph in enumerate(item_paragraphs):
                item_id = f"{section_id}-item-{index}"
                items.append(ResumeItem(item_id=item_id, text=_strip_bullet_prefix(paragraph.text)))
                nodes[item_id] = DocxParagraphNode(item_id, paragraph)
            sections.append(ResumeSection(section_id=section_id, heading=heading, items=items))

        return StructuredResume(sections=sections), nodes
