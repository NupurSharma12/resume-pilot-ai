"""The `DocumentExtractor` protocol and its concrete, per-format implementations.

Every extractor here converts raw file bytes into plain text for exactly
one document format; deciding *which* extractor applies to a given file is
the registry's job (`registry.py`), not any individual extractor's.
"""

from io import BytesIO
from typing import Protocol, runtime_checkable

from docx import Document
from pypdf import PdfReader

from app.ingestion.errors import DocumentExtractionError


@runtime_checkable
class DocumentExtractor(Protocol):
    """Structural interface for a single-format document-to-text extractor."""

    def extract(self, content: bytes) -> str:
        """Convert raw file bytes into plain text."""
        ...


class PdfDocumentExtractor:
    """Extracts text from PDF files using `pypdf`.

    Reads only text embedded directly in the PDF: pages that are scanned
    images with no embedded text layer yield no text for that page, since
    no OCR is performed. That is the correct, intended behavior for a
    "no OCR" extractor, not an error condition.
    """

    def extract(self, content: bytes) -> str:
        """Extract and concatenate the text of every page in the PDF."""
        try:
            reader = PdfReader(BytesIO(content))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DocumentExtractionError(f"Failed to extract text from PDF: {exc}") from exc


class DocxDocumentExtractor:
    """Extracts text from DOCX files using `python-docx`.

    Reads paragraph text only; text inside tables is not extracted. This
    is a deliberate scope limit for this first version, not an oversight —
    most resumes and job descriptions are paragraph-based prose.
    """

    def extract(self, content: bytes) -> str:
        """Extract and concatenate the text of every paragraph in the document."""
        try:
            document = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as exc:
            raise DocumentExtractionError(f"Failed to extract text from DOCX: {exc}") from exc


class MarkdownDocumentExtractor:
    """Extracts text from Markdown files by decoding them as UTF-8.

    Markdown source is not converted to prose: its syntax (headings,
    emphasis, links, ...) is left intact, since Markdown is designed to
    already be readable as plain text, and downstream LLM prompting reads
    Markdown formatting natively. Kept as its own class distinct from
    `PlainTextDocumentExtractor`, even though today's implementation is
    identical, so Markdown-specific handling can be added later without
    touching plain-text handling.
    """

    def extract(self, content: bytes) -> str:
        """Decode the Markdown source as UTF-8 text, unmodified."""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(f"Failed to decode Markdown as UTF-8: {exc}") from exc


class PlainTextDocumentExtractor:
    """Extracts text from plain-text files by decoding them as UTF-8."""

    def extract(self, content: bytes) -> str:
        """Decode the file's bytes as UTF-8 text."""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(f"Failed to decode text as UTF-8: {exc}") from exc
