"""Format-agnostic editable-node abstraction for high-fidelity document editing.

`EditableNode` is the one interface every format-specific editing engine
implements — today `DocxParagraphNode` (see `docx_nodes.py`); a future PDF
fidelity engine would implement the same protocol over whatever PDF gives
it (a text run within a content stream, most likely) without this module,
or anything that depends only on this protocol, needing to change at all.

The operations mirror `app.models.tailoring_suggestions.SuggestionOperation`
deliberately (`append`/`insert_before`/`insert_after`/`update`/`replace`/
`add_emphasis`/`remove`) — this is the execution side of that same
operation vocabulary, not a parallel one. `update`/`replace`/`add_emphasis`
all resolve to `set_text` (full-text replacement); there is no format-level
distinction between them, only a planning-level one (see
`app.models.tailoring_suggestions`' own docstring on why the Planner
prefers one over another).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EditableNode(Protocol):
    """One addressable, in-place-editable unit of a source document.

    Every method mutates the underlying document object directly (in
    contrast to `StructuredResume`, which is immutable data) — that
    in-place mutation, on the *original* document's own objects, is
    exactly what makes high-fidelity editing possible: everything this
    node doesn't touch is untouched, not regenerated.
    """

    node_id: str

    def get_text(self) -> str:
        """Return this node's current, plain text."""
        ...

    def set_text(self, text: str) -> None:
        """Replace this node's full text, preserving its primary formatting.

        Used for `update`/`replace`/`add_emphasis`. See each
        implementation's docstring for exactly which formatting survives
        a full-text replacement — a node with internally mixed formatting
        (e.g. one bolded word mid-sentence) cannot generally preserve
        that internal distinction across an arbitrary new text, and
        implementations must document that honestly rather than silently
        losing it.
        """
        ...

    def append_text(self, addition: str) -> None:
        """Append `addition` to this node's existing text, changing nothing else.

        Used for `append`. Implementations should prefer a technique that
        never touches the node's existing content at all (e.g. adding a
        new formatting run rather than rewriting the whole node), so the
        original portion keeps its exact original formatting, not just an
        approximation of it.
        """
        ...

    def insert_after(self, text: str) -> "EditableNode":
        """Insert a new node with `text`, immediately after this one, and return it.

        Used for `insert_after`. The new node should match this node's
        own formatting (style, list level, indentation, ...), since it's
        anchored as this node's sibling for exactly that reason.
        """
        ...

    def insert_before(self, text: str) -> "EditableNode":
        """Insert a new node with `text`, immediately before this one, and return it.

        Used for `insert_before`. See `insert_after` for the same
        formatting-matching expectation.
        """
        ...

    def remove(self) -> None:
        """Remove this node from the document entirely.

        Used for `remove`. After this call, this node's `node_id` no
        longer resolves to anything in the document.
        """
        ...
