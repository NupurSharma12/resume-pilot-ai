"""Data contracts for the final-resume export layer.

See `app.export.service.ExportService` for how these are produced, and
`docs/features/interactive-tailored-resume.md` for the honesty rules this
module exists to enforce: an export is never labeled as preserving
formatting it did not actually preserve.
"""

from dataclasses import dataclass
from enum import StrEnum


class ExportFormat(StrEnum):
    """A file format the final resume can be downloaded as."""

    TXT = "txt"
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"


class FormatFidelity(StrEnum):
    """How closely an exported file's formatting matches the originally uploaded file.

    Never `EXACT_ORIGINAL` in this version of the application: no
    original file bytes are retained anywhere after upload (see
    `docs/features/interactive-tailored-resume.md`'s "Export behavior and
    limitations" section) — only extracted text survives, so nothing this
    module produces can be a byte-exact reproduction of the source
    document's layout. The type still defines the value so the API
    contract has a place for it if a future version adds real
    round-trippable source retention; it simply isn't reachable today.
    """

    EXACT_ORIGINAL = "exact_original"
    APPROXIMATE_STYLE = "approximate_style"
    REGENERATED_TEMPLATE = "regenerated_template"


@dataclass(frozen=True)
class ExportedFile:
    """One rendered, downloadable file."""

    filename: str
    content_type: str
    content: bytes
    fidelity: FormatFidelity
    fidelity_note: str
