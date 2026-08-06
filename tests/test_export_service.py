"""Unit tests for `ExportService` and its renderers."""

from io import BytesIO

from docx import Document
from pypdf import PdfReader

from app.export.models import ExportFormat, FormatFidelity
from app.export.service import ExportService, sanitize_filename_base
from app.models.resume_structure import ResumeItem, ResumeSection, StructuredResume


def _structured_resume() -> StructuredResume:
    return StructuredResume(
        sections=[
            ResumeSection(
                section_id="section-0",
                heading="SKILLS",
                items=[
                    ResumeItem(item_id="section-0-item-0", text="Python"),
                    ResumeItem(item_id="section-0-item-1", text="Django"),
                ],
            )
        ]
    )


def test_txt_export_contains_all_resume_content() -> None:
    file = ExportService().export(_structured_resume(), ExportFormat.TXT, "My Resume")
    text = file.content.decode("utf-8")
    assert "SKILLS" in text
    assert "Python" in text
    assert "Django" in text
    assert file.content_type == "text/plain"
    assert file.filename == "My_Resume.txt"
    assert file.fidelity == FormatFidelity.APPROXIMATE_STYLE


def test_markdown_export_uses_markdown_syntax() -> None:
    file = ExportService().export(_structured_resume(), ExportFormat.MARKDOWN, "My Resume")
    text = file.content.decode("utf-8")
    assert "## SKILLS" in text
    assert "- Python" in text
    assert file.filename == "My_Resume.md"


def test_docx_export_is_a_valid_readable_document() -> None:
    file = ExportService().export(_structured_resume(), ExportFormat.DOCX, "My Resume")
    document = Document(BytesIO(file.content))
    all_text = "\n".join(p.text for p in document.paragraphs)
    assert "SKILLS" in all_text
    assert "Python" in all_text
    assert "Django" in all_text
    assert file.fidelity == FormatFidelity.REGENERATED_TEMPLATE
    assert file.filename == "My_Resume.docx"


def test_pdf_export_is_a_valid_readable_document() -> None:
    file = ExportService().export(_structured_resume(), ExportFormat.PDF, "My Resume")
    reader = PdfReader(BytesIO(file.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "SKILLS" in text
    assert "Python" in text
    assert file.fidelity == FormatFidelity.REGENERATED_TEMPLATE
    assert file.content_type == "application/pdf"


def test_filename_sanitizes_unsafe_characters() -> None:
    file = ExportService().export(
        _structured_resume(), ExportFormat.TXT, "../../etc/passwd; rm -rf"
    )
    assert file.filename == "etc_passwd_rm_-rf.txt"
    assert "/" not in file.filename
    assert ".." not in file.filename


def test_filename_falls_back_to_default_when_nothing_safe_remains() -> None:
    assert sanitize_filename_base("???") == "Tailored_Resume"
    assert sanitize_filename_base(None) == "Tailored_Resume"
    assert sanitize_filename_base("") == "Tailored_Resume"


def test_pdf_export_of_empty_resume_does_not_crash() -> None:
    empty = StructuredResume(sections=[])
    file = ExportService().export(empty, ExportFormat.PDF, None)
    assert len(file.content) > 0
    assert file.filename == "Tailored_Resume.pdf"
