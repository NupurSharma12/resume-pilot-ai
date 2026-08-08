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
for the one check this module still makes defensively. Multiple
independent `append` suggestions targeting the *same* paragraph are not
only allowed but handled naturally here: each `append_text` call only
ever adds a new run, never touches an earlier one, so composing several
of them is just calling it several times -- no special-casing needed,
unlike `SuggestionApplier`'s text-concatenation equivalent.
"""

from io import BytesIO

from docx import Document

from app.document_editing.docx_nodes import DocxParagraphNode
from app.document_editing.docx_structure_mapper import DocxStructureMapper
from app.document_editing.errors import ConflictingEditsError, EditTargetNotFoundError
from app.models.tailoring_suggestions import SuggestionOperation, TailoringSuggestion
from app.tailoring.applier import compute_append_delta
from app.tailoring.conflicts import compute_conflicts


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
        """Reuses `app.tailoring.conflicts.compute_conflicts` -- the exact same policy
        `SuggestionApplier` enforces, so this module can never disagree with it about
        what counts as a conflict (e.g. multiple independent `append`s to the same
        item are allowed here for precisely the same reason they're allowed there).
        """
        conflicts = compute_conflicts(suggestions)
        by_id = {s.suggestion_id: s for s in suggestions}
        for suggestion_id, other_ids in conflicts.items():
            if other_ids:
                raise ConflictingEditsError(by_id[suggestion_id].target_item_id)

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
