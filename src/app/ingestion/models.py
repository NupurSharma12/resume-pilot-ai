"""Data contracts for the document ingestion layer."""

from enum import StrEnum


class DocumentFormat(StrEnum):
    """A document format the ingestion layer knows how to extract text from."""

    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
