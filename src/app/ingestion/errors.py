"""Exceptions raised by the document ingestion layer.

A single exception family so callers of `DocumentExtractorRegistry.extract`
never need to know which underlying library (`pypdf`, `python-docx`, ...)
produced a given failure — only that extraction failed, and why.
"""


class DocumentExtractionError(Exception):
    """Raised when a document's content could not be extracted to text."""


class UnsupportedDocumentFormatError(DocumentExtractionError):
    """Raised when a filename's extension does not match any supported document format."""
