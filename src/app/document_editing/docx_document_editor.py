"""The DOCX high-fidelity editing engine: mutates only approved paragraphs in place.

`DocxDocumentEditor.apply` is the one place original DOCX bytes actually
get edited. It never rebuilds a document (contrast
`app.export.renderers.DocxResumeRenderer`, which always generates a fresh
one) -- it opens the original file, mutates exactly the paragraphs named
by the given suggestions' `target_item_id`s via `DocxParagraphNode` (see
that module for exactly which formatting each operation preserves), and
re-saves the same `Document` object. Everything the input suggestions
don't target -- other paragraphs, styles, tables, headers, footers, page
breaks, hyperlinks, the whole rest of the OOXML tree -- is never touched,
so it survives byte-for-byte in the parts unrelated to the edit.

Deliberately takes `list[TailoringSuggestion]`, not a looser edit
descriptor: this is designed to consume
`app.tailoring.applier.SuggestionApplier`'s own resolved output directly
(selection/conflict/revalidation already settled there) rather than
re-implementing any of that here. See `ConflictingEditsError`'s docstring
for the one check this module still makes defensively.
"""

from io import BytesIO

from docx import Document

from app.document_editing.docx_nodes import DocxParagraphNode
from app.document_editing.docx_structure_mapper import DocxStructureMapper
from app.document_editing.errors import ConflictingEditsError, EditTargetNotFoundError
from app.models.tailoring_suggestions import (
    REPLACEMENT_OPERATIONS,
    SuggestionOperation,
    TailoringSuggestion,
)


def compute_append_delta(current_text: str, suggested_text: str) -> str:
    """Recover just the newly-appended portion of an `append` suggestion's full text.

    `suggested_text` for `append` is always the item's full resulting
    text (existing text + addition), per this pipeline's own contract
    (enforced server-side at generation time -- see
    `app.evidence.suggestion_validator`). `DocxParagraphNode.append_text`
    needs only the addition, not the whole paragraph again, so this
    strips `current_text` back out.

    Deliberately preserves whatever separator punctuation/whitespace the
    model put between the original and added text (e.g. the ", " in
    "Python" -> "Python, TypeScript") rather than trimming it -- this
    result is concatenated directly onto the existing DOCX text, unlike
    the frontend's display-only equivalent
    (`suggestionPresentation.ts`'s `computeAppendedDelta`), which trims
    leading punctuation because it's presenting the delta on its own,
    never concatenating it. Falls back to the full suggested text if
    `current_text` genuinely isn't a substring -- unreachable given that
    same server-side validation, but handled rather than assumed.
    """
    index = suggested_text.find(current_text)
    if index == -1:
        return suggested_text
    # Content strictly after `current_text` is the genuinely new part;
    # any content *before* it (unusual for an append, but not impossible)
    # is folded in too, rather than silently dropped.
    before = suggested_text[:index]
    after = suggested_text[index + len(current_text) :]
    return before + after


class DocxDocumentEditor:
    """Applies a batch of already-resolved suggestions to an original DOCX's bytes."""

    def apply(self, original_docx_bytes: bytes, suggestions: list[TailoringSuggestion]) -> bytes:
        """Return new DOCX bytes with only `suggestions`' target paragraphs changed.

        `suggestions` must already be conflict-free and carry whatever
        edited text the user approved (exactly
        `SuggestionApplier.apply`'s resolved suggestion list) -- this
        method re-derives the document's node map fresh from
        `original_docx_bytes` each call (never caches one across calls),
        so it only ever mutates the exact `Document` object it's about to
        save, never a stale one.
        """
        document = Document(BytesIO(original_docx_bytes))
        _, nodes = DocxStructureMapper().map(document)

        self._check_no_conflicts(suggestions)
        for suggestion in suggestions:
            node = nodes.get(suggestion.target_item_id)
            if node is None:
                raise EditTargetNotFoundError(suggestion.target_item_id)
            self._apply_one(node, suggestion)

        buffer = BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _check_no_conflicts(suggestions: list[TailoringSuggestion]) -> None:
        """Mirrors `SuggestionApplier._check_conflicts`'s exact category policy.

        Two suggestions only conflict if they'd both determine the same
        physical outcome: both mutate the same target item's own content
        (any two of `REPLACEMENT_OPERATIONS`), or both insert at the same
        position relative to the same anchor (two `insert_before`, or two
        `insert_after`, targeting the same item). An `insert_before`/
        `insert_after` never conflicts with a mutation of its own anchor
        -- they touch different physical positions. Using a coarser
        "same target_item_id" rule here would reject batches
        `SuggestionApplier` itself already approved as conflict-free.
        """
        seen: set[tuple[str, str]] = set()
        for suggestion in suggestions:
            category = (
                "mutate"
                if suggestion.operation in REPLACEMENT_OPERATIONS
                else suggestion.operation.value
            )
            key = (suggestion.target_item_id, category)
            if key in seen:
                raise ConflictingEditsError(suggestion.target_item_id)
            seen.add(key)

    @staticmethod
    def _apply_one(node: DocxParagraphNode, suggestion: TailoringSuggestion) -> None:
        operation = suggestion.operation
        if operation == SuggestionOperation.APPEND:
            delta = compute_append_delta(suggestion.current_text or "", suggestion.suggested_text)
            node.append_text(delta)
        elif operation in (
            SuggestionOperation.UPDATE,
            SuggestionOperation.REPLACE,
            SuggestionOperation.ADD_EMPHASIS,
        ):
            node.set_text(suggestion.suggested_text)
        elif operation == SuggestionOperation.REMOVE:
            node.remove()
        elif operation == SuggestionOperation.INSERT_BEFORE:
            node.insert_before(suggestion.suggested_text)
        elif operation == SuggestionOperation.INSERT_AFTER:
            node.insert_after(suggestion.suggested_text)
