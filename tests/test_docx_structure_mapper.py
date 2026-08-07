"""Unit tests for `DocxStructureMapper`."""

from app.document_editing.docx_nodes import DocxParagraphNode
from app.document_editing.docx_structure_mapper import DocxStructureMapper
from tests.document_editing_fixtures import build_sample_docx_bytes, open_docx


def _map():
    document = open_docx(build_sample_docx_bytes())
    return DocxStructureMapper().map(document)


def test_headings_are_detected_from_real_paragraphs() -> None:
    structured, _ = _map()

    headings = [section.heading for section in structured.sections]
    assert headings == ["SUMMARY", "SKILLS", "EXPERIENCE"]


def test_each_paragraph_becomes_exactly_one_item_no_line_joining_needed() -> None:
    structured, _ = _map()

    skills_section = next(s for s in structured.sections if s.heading == "SKILLS")
    assert [item.text for item in skills_section.items] == ["Python", "Django"]


def test_item_and_section_ids_match_the_node_map_keys_exactly() -> None:
    structured, nodes = _map()

    all_item_ids = {item.item_id for section in structured.sections for item in section.items}
    assert all_item_ids == set(nodes.keys())


def test_nodes_are_docx_paragraph_nodes_wrapping_the_real_paragraph() -> None:
    structured, nodes = _map()

    skills_section = next(s for s in structured.sections if s.heading == "SKILLS")
    python_item = skills_section.items[0]
    node = nodes[python_item.item_id]
    assert isinstance(node, DocxParagraphNode)
    assert node.get_text() == "Python"


def test_table_paragraphs_are_not_mapped() -> None:
    structured, _ = _map()

    all_text = {item.text for section in structured.sections for item in section.items}
    assert "Skill" not in all_text
    assert "Years" not in all_text


def test_header_and_footer_paragraphs_are_not_mapped() -> None:
    structured, _ = _map()

    all_text = {item.text for section in structured.sections for item in section.items}
    assert "Nupur Sharma — Resume" not in all_text
    assert "Page 1" not in all_text


def test_blank_paragraphs_do_not_become_items() -> None:
    structured, nodes = _map()

    for section in structured.sections:
        for item in section.items:
            assert item.text.strip() != ""
    assert all(node.get_text().strip() for node in nodes.values())


def test_a_typed_bullet_character_is_stripped_from_item_text_but_not_from_the_node() -> None:
    from io import BytesIO

    document = open_docx(build_sample_docx_bytes())
    summary_paragraph = next(
        p for p in document.paragraphs if p.text == "Backend engineer with 5 years of experience."
    )
    summary_paragraph.text = "• Manually typed bullet"

    buffer = BytesIO()
    document.save(buffer)

    structured, nodes = DocxStructureMapper().map(open_docx(buffer.getvalue()))
    summary_section = next(s for s in structured.sections if s.heading == "SUMMARY")
    item = summary_section.items[0]
    assert item.text == "Manually typed bullet"
    # The underlying node's real text is untouched -- stripping only
    # affects the item's *display* text used for suggestion generation.
    assert nodes[item.item_id].get_text() == "• Manually typed bullet"
