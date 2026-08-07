"""`EditableNode` for DOCX: one `python-docx` `Paragraph`, edited in place.

This is the only module in the codebase that manipulates a `Paragraph`'s
underlying OOXML directly (`paragraph._p`, the `<w:p>` element). That
escape hatch — private by Python convention, but a stable, widely-used
technique in the `python-docx` ecosystem precisely because the public API
has no "insert a paragraph here" or "clone this paragraph's formatting"
method — is deliberately confined to this one module, so the rest of the
codebase never needs to know DOCX/OOXML exists.
"""

from copy import deepcopy
from uuid import uuid4

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run


class DocxParagraphNode:
    """Wraps one live `Paragraph` from an already-opened `python-docx` `Document`.

    Every mutation here happens on `paragraph`'s own OOXML elements, in
    the same in-memory `Document` object the caller opened — nothing is
    copied into a new document or re-rendered. Saving that `Document`
    afterward (`document.save(...)`) is what turns these in-place edits
    into the final file; this class itself never touches file I/O.
    """

    def __init__(self, node_id: str, paragraph: Paragraph) -> None:
        self.node_id = node_id
        self._paragraph = paragraph

    def get_text(self) -> str:
        return self._paragraph.text

    def set_text(self, text: str) -> None:
        """Full-text replacement: keeps the first run's formatting, drops the rest.

        A paragraph with a single run (the common case for one resume
        bullet) preserves its formatting exactly. A paragraph with
        *multiple* runs of genuinely different formatting (e.g. a bolded
        company name mid-sentence) collapses to the first run's
        formatting for the whole new text — there is no general way to
        know which formatting should apply to arbitrary new text spanning
        what used to be several runs, and guessing would be worse than
        being upfront about it (see `EditableNode.set_text`'s docstring).
        """
        runs = list(self._paragraph.runs)
        if not runs:
            self._paragraph.add_run(text)
            return
        runs[0].text = text
        for extra_run in runs[1:]:
            self._remove_run(extra_run)

    def append_text(self, addition: str) -> None:
        """Adds a new run for `addition`, cloned from the last run's formatting.

        Existing runs are never touched, so the original text keeps its
        exact original formatting (not an approximation of it) — this is
        the one operation that achieves true full fidelity even for a
        paragraph with internally mixed formatting.
        """
        if not addition:
            return
        existing_runs = list(self._paragraph.runs)
        new_run = self._paragraph.add_run(addition)
        if existing_runs:
            source_run_properties = existing_runs[-1]._r.find(qn("w:rPr"))
            if source_run_properties is not None:
                new_run._r.insert(0, deepcopy(source_run_properties))

    def insert_after(self, text: str) -> "DocxParagraphNode":
        return self._insert_sibling(text, after=True)

    def insert_before(self, text: str) -> "DocxParagraphNode":
        return self._insert_sibling(text, after=False)

    def remove(self) -> None:
        parent = self._paragraph._p.getparent()
        if parent is not None:
            parent.remove(self._paragraph._p)

    def _insert_sibling(self, text: str, *, after: bool) -> "DocxParagraphNode":
        """Clones this paragraph's element (style, numbering, indentation and all).

        Cloning the whole `<w:p>` — rather than creating a blank
        paragraph and copying properties field by field — is what
        guarantees the new paragraph matches this one's formatting
        exactly (list bullet/numbering included), since it inherits
        every property this paragraph has, known or not.
        """
        cloned_element = deepcopy(self._paragraph._p)
        if after:
            self._paragraph._p.addnext(cloned_element)
        else:
            self._paragraph._p.addprevious(cloned_element)
        cloned_paragraph = Paragraph(cloned_element, self._paragraph._parent)
        new_node = DocxParagraphNode(f"{self.node_id}-new-{uuid4().hex[:8]}", cloned_paragraph)
        new_node.set_text(text)
        return new_node

    @staticmethod
    def _remove_run(run: Run) -> None:
        parent = run._r.getparent()
        if parent is not None:
            parent.remove(run._r)
