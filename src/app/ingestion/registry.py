"""Dispatches document extraction to the right format-specific `DocumentExtractor`."""

from collections.abc import Mapping
from pathlib import Path

from app.ingestion.errors import UnsupportedDocumentFormatError
from app.ingestion.extractor import (
    DocumentExtractor,
    DocxDocumentExtractor,
    MarkdownDocumentExtractor,
    PdfDocumentExtractor,
    PlainTextDocumentExtractor,
)
from app.ingestion.models import DocumentFormat

_EXTENSION_TO_FORMAT: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
    ".txt": DocumentFormat.PLAIN_TEXT,
}


class DocumentExtractorRegistry:
    """Selects and invokes the correct `DocumentExtractor` for a given filename.

    Takes its `extractors` mapping via constructor injection — the same
    dependency-injection pattern `ResumeAnalysisWorkflow` uses for its own
    collaborators — rather than hardcoding which concrete extractor backs
    each format.
    """

    def __init__(self, extractors: Mapping[DocumentFormat, DocumentExtractor]) -> None:
        """Store the injected format-to-extractor mapping for use by `extract`."""
        self._extractors = dict(extractors)

    def extract(self, content: bytes, filename: str) -> str:
        """Detect `filename`'s format and extract `content` to plain text.

        Raises `UnsupportedDocumentFormatError` if `filename`'s extension
        does not match any supported document format — the one
        user-facing failure mode this method documents. If the extension
        *is* recognized but this registry instance happens to have no
        extractor registered for it, that reflects a bug in how the
        registry was constructed (see `build_default_document_extractor_registry`),
        not something a caller should need to catch: it surfaces as a
        plain `KeyError`, kept deliberately distinct from
        `UnsupportedDocumentFormatError`.
        """
        document_format = self._detect_format(filename)
        extractor = self._extractors[document_format]
        return extractor.extract(content)

    def _detect_format(self, filename: str) -> DocumentFormat:
        """Map `filename`'s extension to a `DocumentFormat`.

        Private: callers use `extract`, which calls this internally.
        Matching is case-insensitive, since real-world filenames aren't
        reliably lowercase (e.g. `"Resume.PDF"`).
        """
        suffix = Path(filename).suffix.lower()
        try:
            return _EXTENSION_TO_FORMAT[suffix]
        except KeyError:
            raise UnsupportedDocumentFormatError(
                f"Unsupported file extension: {suffix!r}"
            ) from None


def build_default_document_extractor_registry() -> DocumentExtractorRegistry:
    """Build a `DocumentExtractorRegistry` wired with all four supported extractors.

    A plain factory function, not a FastAPI dependency: this stays
    framework-agnostic so a future API-layer dependency provider can call
    it without requiring changes here.
    """
    return DocumentExtractorRegistry(
        extractors={
            DocumentFormat.PDF: PdfDocumentExtractor(),
            DocumentFormat.DOCX: DocxDocumentExtractor(),
            DocumentFormat.MARKDOWN: MarkdownDocumentExtractor(),
            DocumentFormat.PLAIN_TEXT: PlainTextDocumentExtractor(),
        }
    )
