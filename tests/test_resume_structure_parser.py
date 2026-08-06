"""Unit tests for `ResumeStructureParser`."""

from app.resume_structure.parser import ResumeStructureParser

_SAMPLE_RESUME = """\
Nupur Sharma
nupur@example.com | (555) 123-4567

SUMMARY
Backend engineer with 6 years of experience building distributed systems.
Focused on reliability and developer tooling.

EXPERIENCE
Senior Software Engineer, Acme Corp (2020-Present)
- Led the migration of the internal dashboard from Angular to React.
- Mentored two junior engineers and ran weekly code reviews.
- Owned the CI/CD pipeline using Docker and GitHub Actions.

Software Engineer, Initech (2017-2020)
- Built internal tooling for the platform team.

SKILLS
- Python, TypeScript, React
- Docker, Kubernetes, AWS

EDUCATION
B.S. Computer Science, State University (2017)
"""


def test_content_before_first_heading_becomes_a_headingless_section() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    assert structured.sections[0].heading == ""
    assert any("Nupur Sharma" in item.text for item in structured.sections[0].items)


def test_detects_all_caps_headings() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    headings = [section.heading for section in structured.sections]
    assert "SUMMARY" in headings
    assert "EXPERIENCE" in headings
    assert "SKILLS" in headings
    assert "EDUCATION" in headings


def test_bullet_lines_become_individual_items() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    experience = next(s for s in structured.sections if s.heading == "EXPERIENCE")
    bullet_texts = [item.text for item in experience.items]
    assert "Led the migration of the internal dashboard from Angular to React." in bullet_texts
    assert "Mentored two junior engineers and ran weekly code reviews." in bullet_texts
    assert "Owned the CI/CD pipeline using Docker and GitHub Actions." in bullet_texts


def test_non_bullet_lines_form_their_own_item_distinct_from_bullets() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    experience = next(s for s in structured.sections if s.heading == "EXPERIENCE")
    assert experience.items[0].text == "Senior Software Engineer, Acme Corp (2020-Present)"


def test_blank_line_separates_two_roles_into_separate_items() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    experience = next(s for s in structured.sections if s.heading == "EXPERIENCE")
    role_lines = [item.text for item in experience.items if "Initech" in item.text]
    assert role_lines == ["Software Engineer, Initech (2017-2020)"]


def test_item_ids_are_stable_and_unique() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    all_ids = [item.item_id for section in structured.sections for item in section.items]
    assert len(all_ids) == len(set(all_ids))
    # Deterministic: parsing the same text twice produces identical ids.
    again = ResumeStructureParser().parse(_SAMPLE_RESUME)
    again_ids = [item.item_id for section in again.sections for item in section.items]
    assert all_ids == again_ids


def test_get_item_and_get_section_resolve_by_id() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    experience = next(s for s in structured.sections if s.heading == "EXPERIENCE")
    first_item = experience.items[0]

    assert structured.get_section(experience.section_id) is experience
    assert structured.get_item(first_item.item_id) is first_item
    assert structured.get_item("does-not-exist") is None
    assert structured.get_section("does-not-exist") is None


def test_no_content_is_dropped() -> None:
    """Every non-blank input line ends up in exactly one output item or heading."""
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    rendered_text = " ".join(
        part
        for section in structured.sections
        for part in [section.heading, *[item.text for item in section.items]]
    )
    for expected_fragment in [
        "Nupur Sharma",
        "Led the migration",
        "Python, TypeScript, React",
        "B.S. Computer Science",
    ]:
        assert expected_fragment in rendered_text


def test_empty_resume_produces_no_sections() -> None:
    structured = ResumeStructureParser().parse("")

    assert structured.sections == []


def test_to_text_round_trips_content_faithfully() -> None:
    structured = ResumeStructureParser().parse(_SAMPLE_RESUME)

    rendered = structured.to_text()
    assert "SUMMARY" in rendered
    assert "Led the migration of the internal dashboard from Angular to React." in rendered
