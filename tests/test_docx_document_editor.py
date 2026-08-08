"""Unit tests for `DocxDocumentEditor`."""

import pytest

from app.document_editing.docx_document_editor import DocxDocumentEditor, compute_append_delta
from app.document_editing.docx_structure_mapper import DocxStructureMapper
from app.document_editing.errors import ConflictingEditsError, EditTargetNotFoundError
from app.models.tailoring_suggestions import SuggestionOperation
from tests.document_editing_fixtures import build_sample_docx_bytes, make_suggestion, open_docx


def _item_id(structured, text: str) -> tuple[str, str]:
    for section in structured.sections:
        for item in section.items:
            if item.text == text:
                return section.section_id, item.item_id
    raise AssertionError(f"No item found with text {text!r}")


class TestComputeAppendDelta:
    def test_recovers_only_the_new_portion_including_its_separator(self) -> None:
        assert compute_append_delta("Python", "Python, TypeScript") == ", TypeScript"

    def test_falls_back_to_the_full_text_when_current_text_is_not_a_substring(self) -> None:
        assert compute_append_delta("Not present", "Something else") == "Something else"


class TestDocxDocumentEditorApply:
    def test_update_replaces_text_and_preserves_paragraph_formatting(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Backend engineer with 5 years of experience.")
        suggestion = make_suggestion(
            "s1",
            section_id,
            item_id,
            SuggestionOperation.UPDATE,
            "Backend engineer with 5 years of experience.",
            "Full-stack engineer with React and Python experience.",
        )

        edited_bytes = DocxDocumentEditor().apply(original, [suggestion])
        edited = open_docx(edited_bytes)

        paragraph = next(
            p
            for p in edited.paragraphs
            if p.text == "Full-stack engineer with React and Python experience."
        )
        assert paragraph.runs[0].font.size is not None

    def test_append_preserves_original_run_and_clones_formatting_for_the_addition(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestion = make_suggestion(
            "s1", section_id, item_id, SuggestionOperation.APPEND, "Python", "Python, TypeScript"
        )

        edited_bytes = DocxDocumentEditor().apply(original, [suggestion])
        edited = open_docx(edited_bytes)

        paragraph = next(p for p in edited.paragraphs if p.text == "Python, TypeScript")
        assert paragraph.runs[0].text == "Python"
        assert paragraph.runs[0].bold is True
        assert paragraph.runs[1].bold is True

    def test_insert_after_adds_a_new_bullet_matching_its_neighbor(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestion = make_suggestion(
            "s1", section_id, item_id, SuggestionOperation.INSERT_AFTER, None, "Node.js"
        )

        edited_bytes = DocxDocumentEditor().apply(original, [suggestion])
        edited = open_docx(edited_bytes)

        texts = [p.text for p in edited.paragraphs]
        assert "Node.js" in texts
        assert texts.index("Python") < texts.index("Node.js") < texts.index("Django")

    def test_remove_deletes_the_target_paragraph_only(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Irrelevant certification from 2005.")
        suggestion = make_suggestion(
            "s1",
            section_id,
            item_id,
            SuggestionOperation.REMOVE,
            "Irrelevant certification from 2005.",
            "",
        )

        edited_bytes = DocxDocumentEditor().apply(original, [suggestion])
        edited = open_docx(edited_bytes)

        texts = [p.text for p in edited.paragraphs]
        assert "Irrelevant certification from 2005." not in texts
        assert "Built internal tools using Python and Django." in texts

    def test_unaffected_paragraphs_tables_headers_and_footers_survive_untouched(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestion = make_suggestion(
            "s1", section_id, item_id, SuggestionOperation.APPEND, "Python", "Python, TypeScript"
        )

        edited_bytes = DocxDocumentEditor().apply(original, [suggestion])
        edited = open_docx(edited_bytes)
        original_doc = open_docx(original)

        assert "Django" in [p.text for p in edited.paragraphs]
        assert len(edited.tables) == len(original_doc.tables)
        assert edited.tables[0].rows[0].cells[0].text == "Skill"
        assert edited.tables[0].rows[0].cells[1].text == "Years"
        assert edited.sections[0].header.paragraphs[0].text == "Nupur Sharma — Resume"
        assert edited.sections[0].footer.paragraphs[0].text == "Page 1"

    def test_multiple_independent_edits_in_one_batch_all_apply(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        _, python_id = _item_id(structured, "Python")
        summary_section_id, summary_id = _item_id(
            structured, "Backend engineer with 5 years of experience."
        )
        skills_section_id, _ = _item_id(structured, "Python")
        suggestions = [
            make_suggestion(
                "s1",
                summary_section_id,
                summary_id,
                SuggestionOperation.UPDATE,
                "Backend engineer with 5 years of experience.",
                "Full-stack engineer.",
            ),
            make_suggestion(
                "s2",
                skills_section_id,
                python_id,
                SuggestionOperation.APPEND,
                "Python",
                ", TypeScript",
            ),
        ]

        edited_bytes = DocxDocumentEditor().apply(original, suggestions)
        texts = [p.text for p in open_docx(edited_bytes).paragraphs]

        assert "Full-stack engineer." in texts
        assert "Python, TypeScript" in texts

    def test_unknown_target_item_id_raises(self) -> None:
        original = build_sample_docx_bytes()
        suggestion = make_suggestion(
            "s1", "section-1", "section-1-item-99", SuggestionOperation.UPDATE, "x", "y"
        )

        with pytest.raises(EditTargetNotFoundError, match="section-1-item-99"):
            DocxDocumentEditor().apply(original, [suggestion])

    def test_two_mutations_of_the_same_item_conflict(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestions = [
            make_suggestion(
                "s1", section_id, item_id, SuggestionOperation.APPEND, "Python", "Python, TS"
            ),
            make_suggestion(
                "s2", section_id, item_id, SuggestionOperation.UPDATE, "Python", "Python expert"
            ),
        ]

        with pytest.raises(ConflictingEditsError, match=item_id):
            DocxDocumentEditor().apply(original, suggestions)

    def test_append_and_insert_after_on_the_same_anchor_do_not_conflict(self) -> None:
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestions = [
            make_suggestion(
                "s1",
                section_id,
                item_id,
                SuggestionOperation.APPEND,
                "Python",
                "Python, TypeScript",
            ),
            make_suggestion(
                "s2", section_id, item_id, SuggestionOperation.INSERT_AFTER, None, "Node.js"
            ),
        ]

        edited_bytes = DocxDocumentEditor().apply(original, suggestions)
        texts = [p.text for p in open_docx(edited_bytes).paragraphs]

        assert "Python, TypeScript" in texts
        assert "Node.js" in texts

    def test_multiple_independent_appends_to_the_same_paragraph_compose(self) -> None:
        """The exact motivating scenario: several atomic evidence-additions to one line."""
        original = build_sample_docx_bytes()
        structured, _ = DocxStructureMapper().map(open_docx(original))
        section_id, item_id = _item_id(structured, "Python")
        suggestions = [
            make_suggestion(
                "s1",
                section_id,
                item_id,
                SuggestionOperation.APPEND,
                "Python",
                "Python, TypeScript",
            ),
            make_suggestion(
                "s2",
                section_id,
                item_id,
                SuggestionOperation.APPEND,
                "Python",
                "Python, and Node.js",
            ),
        ]

        edited_bytes = DocxDocumentEditor().apply(original, suggestions)
        edited = open_docx(edited_bytes)

        paragraph = next(p for p in edited.paragraphs if p.text.startswith("Python"))
        assert paragraph.text == "Python, TypeScript, and Node.js"
        # Both additions landed as their own runs -- the original "Python"
        # run was never touched.
        assert paragraph.runs[0].text == "Python"
        assert paragraph.runs[0].bold is True

    def test_no_edits_leaves_all_text_unchanged(self) -> None:
        original = build_sample_docx_bytes()

        edited_bytes = DocxDocumentEditor().apply(original, [])

        original_texts = [p.text for p in open_docx(original).paragraphs]
        edited_texts = [p.text for p in open_docx(edited_bytes).paragraphs]
        assert original_texts == edited_texts
