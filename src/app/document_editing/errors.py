"""Exceptions raised by the high-fidelity document editing layer."""


class DocumentEditingError(Exception):
    """Base class for every error this layer raises."""


class EditTargetNotFoundError(DocumentEditingError):
    """Raised when an edit's `target_item_id` doesn't resolve to any node in the document.

    Reachable if a suggestion was generated against a different
    `StructuredResume` than the one actually mapped from the document
    being edited (e.g. stale ids after the source document changed) --
    callers should treat this the same as `SuggestionApplier`'s
    `UnknownSuggestionIdError`: a sign of a stale/mismatched request, not
    something to silently skip.
    """

    def __init__(self, target_item_id: str) -> None:
        super().__init__(f"No document node found for target_item_id {target_item_id!r}.")
        self.target_item_id = target_item_id


class ConflictingEditsError(DocumentEditingError):
    """Raised when two edits in the same batch target the same document node.

    `DocxDocumentEditor` trusts its caller to have already resolved
    conflicts (see `app.tailoring.applier.SuggestionApplier`, whose
    output this is designed to consume directly) -- this is a defensive
    check for callers that use this layer independently, not the primary
    place conflicts are expected to be caught.
    """

    def __init__(self, target_item_id: str) -> None:
        super().__init__(f"Multiple edits target the same node: {target_item_id!r}.")
        self.target_item_id = target_item_id
