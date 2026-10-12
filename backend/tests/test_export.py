import pytest

from app import export, parsing
from app.main import enforce_invariants
from app.schemas import ContactItem, ExperienceItem, ProjectItem


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("jane@example.com", "mailto:jane@example.com"),
        ("+91 98100 12345", "tel:+919810012345"),
        ("github.com/jane", "https://github.com/jane"),
        ("https://jane.dev", "https://jane.dev"),
        ("jane.github.io", "https://jane.github.io"),
        ("Delhi NCR, India", ""),
    ],
)
def test_contact_url_derivation(text, url):
    assert export.contact_url(ContactItem(text=text, url="")) == url


def test_explicit_contact_url_wins():
    assert export.contact_url(ContactItem(text="LinkedIn", url="https://linkedin.com/in/x")) == "https://linkedin.com/in/x"


def test_pdf_links_survive_export_and_reparse(sample_resume):
    pdf = export.to_pdf(sample_resume).content
    urls = {link.url for link in parsing.extract("cv.pdf", pdf).links}
    assert {"mailto:priya@example.com", "https://linkedin.com/in/priya", "https://github.com/priya/inventory"} <= urls


def test_docx_links_survive_export_and_reparse(sample_resume):
    docx = export.to_docx(sample_resume)
    links = {link.url: link.text for link in parsing.extract("cv.docx", docx).links}
    assert links["https://linkedin.com/in/priya"] == "LinkedIn"
    assert links["https://github.com/priya/inventory"] == "Inventory Tracker"


def _long_resume(base, roles=4, bullets=7):
    resume = base.model_copy(deep=True)
    resume.experience = [
        ExperienceItem(
            title=f"Engineer {i}", company=f"Company {i}", location="Remote", dates="2020 – 2021",
            bullets=["Built and operated a distributed data pipeline processing millions of events per day "
                     "with Python, Kafka and PostgreSQL for analytics teams"] * bullets,
        )
        for i in range(roles)
    ]
    return resume


def test_fit_to_one_page_shrinks_layout(sample_resume):
    resume = _long_resume(sample_resume, roles=3, bullets=5)
    natural = export.to_pdf(resume, "two")
    fitted = export.to_pdf(resume, "one")
    assert natural.pages == 2 and natural.scale == 1.0
    assert fitted.pages == 1 and fitted.scale < 1.0


def test_fit_gives_up_gracefully_when_content_is_too_long(sample_resume):
    result = export.to_pdf(_long_resume(sample_resume, roles=6, bullets=8), "one")
    assert result.pages > 1
    assert result.scale == export.MIN_SCALE


def test_multiline_items_are_folded(sample_resume):
    sample_resume.extra_sections[0].items = ["IBM RAG Certificate\n - Coursera, 8 courses"]
    text = parsing.extract("cv.pdf", export.to_pdf(sample_resume).content).text
    assert "IBM RAG Certificate — Coursera, 8 courses" in text


def test_invariants_keep_project_links_and_drop_invented_projects(sample_resume):
    tailored = sample_resume.model_copy(deep=True)
    tailored.projects = [
        ProjectItem(name="inventory tracker", details="changed", url="", bullets=["Rewritten bullet"]),
        ProjectItem(name="Made-up Project", details="", url="", bullets=["Invented"]),
    ]
    result = enforce_invariants(sample_resume, tailored, ["projects"])
    assert [p.name for p in result.projects] == ["Inventory Tracker"]
    assert result.projects[0].url == "https://github.com/priya/inventory"
    assert result.projects[0].details == "Django, PostgreSQL"
    assert result.projects[0].bullets == ["Rewritten bullet"]
