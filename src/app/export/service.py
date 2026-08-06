"""Assembles a downloadable file from a final `StructuredResume`: content, filename, and label.

`ExportService` is the single place that decides three things together
for one export request: which renderer produces the bytes, what fidelity
claim is honest to make about the result, and what filename is safe to
serve it under. Keeping these three decisions in one place is what
prevents, e.g., a DOCX export ever being mislabeled as style-preserving,
or a filename ever leaking a client-supplied path.
"""

import re
from pathlib import Path
from typing import ClassVar

from app.export.models import ExportedFile, ExportFormat, FormatFidelity
from app.export.renderers import (
    DocxResumeRenderer,
    MarkdownResumeRenderer,
    PdfResumeRenderer,
    TxtResumeRenderer,
)
from app.ingestion.models import DocumentFormat
from app.models.resume_structure import StructuredResume

_CONTENT_TYPES: dict[ExportFormat, str] = {
    ExportFormat.TXT: "text/plain",
    ExportFormat.MARKDOWN: "text/markdown",
    ExportFormat.DOCX: ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ExportFormat.PDF: "application/pdf",
}

_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.TXT: "txt",
    ExportFormat.MARKDOWN: "md",
    ExportFormat.DOCX: "docx",
    ExportFormat.PDF: "pdf",
}

# TXT/Markdown exports faithfully reproduce the final resume's *content*
# but not the original file's exact whitespace/line breaks (see
# `StructuredResume.to_text`'s docstring) -- a real but partial fidelity
# claim. DOCX and PDF are always freshly generated documents: no original
# styling, fonts, or layout ever survive past upload (see
# `docs/features/interactive-tailored-resume.md`), so both are always
# `REGENERATED_TEMPLATE`, regardless of what format was originally
# uploaded.
_FIDELITY: dict[ExportFormat, tuple[FormatFidelity, str]] = {
    ExportFormat.TXT: (
        FormatFidelity.APPROXIMATE_STYLE,
        "Plain-text content matches the final resume; exact original spacing and "
        "line breaks are not guaranteed to be preserved.",
    ),
    ExportFormat.MARKDOWN: (
        FormatFidelity.APPROXIMATE_STYLE,
        "Content matches the final resume, rendered as clean Markdown; the original "
        "file's exact Markdown syntax and spacing are not guaranteed to be preserved.",
    ),
    ExportFormat.DOCX: (
        FormatFidelity.REGENERATED_TEMPLATE,
        "Generated fresh as a DOCX file in a clean, ATS-friendly layout. The original "
        "document's fonts, colors, and layout are not preserved -- only its text "
        "content was retained after upload.",
    ),
    ExportFormat.PDF: (
        FormatFidelity.REGENERATED_TEMPLATE,
        "Generated fresh as an ATS-friendly PDF. This is not a reproduction of any "
        "original document's layout -- no original file bytes are retained after "
        "upload, so exact source formatting can never be preserved for PDF.",
    ),
}

# Maps an originally uploaded format to the export format that counts as
# "the original format" for that upload -- what the review UI's default
# download option resolves to. PDF has no entry: per this feature's
# explicit scope, a PDF upload never defaults to a PDF "preserving" the
# source, since nothing about the source layout was retained -- the
# frontend falls back to offering PDF only as a clearly-labeled
# regenerated option, not as the pre-selected default.
ORIGINAL_FORMAT_EXPORT: dict[DocumentFormat, ExportFormat] = {
    DocumentFormat.PLAIN_TEXT: ExportFormat.TXT,
    DocumentFormat.MARKDOWN: ExportFormat.MARKDOWN,
    DocumentFormat.DOCX: ExportFormat.DOCX,
}

_EXTENSION_TO_SOURCE_FORMAT: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
    ".txt": DocumentFormat.PLAIN_TEXT,
}


def detect_source_format(filename: str | None) -> DocumentFormat | None:
    """Infer the originally uploaded document's format from its filename's extension.

    Returns `None` for an unrecognized or missing filename -- callers
    treat that the same as "no format-specific default available" and
    fall back to `ExportFormat.TXT`. Only the filename string is
    inspected; no file content is read, since none is retained after
    upload (see `docs/features/interactive-tailored-resume.md`).
    """
    if not filename:
        return None
    return _EXTENSION_TO_SOURCE_FORMAT.get(Path(filename).suffix.lower())


_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
_DEFAULT_FILENAME_BASE = "Tailored_Resume"
_MAX_FILENAME_BASE_LENGTH = 80


def sanitize_filename_base(raw: str | None) -> str:
    """Turn arbitrary client-supplied text into a safe filename stem.

    Never used to construct a filesystem path -- only the `filename`
    field of a `Content-Disposition` header -- but sanitized regardless,
    since that header value still reaches a client's filesystem once
    downloaded. Only `[A-Za-z0-9_-]` survive; anything else (including
    path separators, dots, whitespace) becomes `_`. Falls back to a fixed
    default if nothing safe remains, so a filename is never empty.
    """
    if not raw:
        return _DEFAULT_FILENAME_BASE
    cleaned = _SAFE_FILENAME_CHARS.sub("_", raw).strip("_")
    cleaned = cleaned[:_MAX_FILENAME_BASE_LENGTH].strip("_")
    return cleaned or _DEFAULT_FILENAME_BASE


class ExportService:
    """Renders a `StructuredResume` into one `ExportedFile` for a requested `ExportFormat`."""

    _RENDERERS: ClassVar[dict] = {
        ExportFormat.TXT: TxtResumeRenderer(),
        ExportFormat.MARKDOWN: MarkdownResumeRenderer(),
        ExportFormat.DOCX: DocxResumeRenderer(),
        ExportFormat.PDF: PdfResumeRenderer(),
    }

    def export(
        self,
        structured_resume: StructuredResume,
        export_format: ExportFormat,
        filename_base: str | None,
    ) -> ExportedFile:
        """Render `structured_resume` as `export_format` and package it for download.

        `filename_base` is sanitized here (never trusted as-is) and the
        file extension is always derived from `export_format` itself,
        never from any client-supplied name -- so a client cannot cause
        a mismatched extension/content-type pair.
        """
        renderer = self._RENDERERS[export_format]
        content = renderer.render(structured_resume)

        fidelity, fidelity_note = _FIDELITY[export_format]
        safe_base = sanitize_filename_base(filename_base)
        extension = _EXTENSIONS[export_format]

        return ExportedFile(
            filename=f"{safe_base}.{extension}",
            content_type=_CONTENT_TYPES[export_format],
            content=content,
            fidelity=fidelity,
            fidelity_note=fidelity_note,
        )
