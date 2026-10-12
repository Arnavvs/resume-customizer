import pytest

from app import scoring


@pytest.mark.parametrize(
    ("text", "keyword", "expected"),
    [
        ("Worked with Java and Spring", "Java", True),
        ("Built apps in JavaScript", "Java", False),
        ("Strong C++ and C# skills", "C++", True),
        ("Strong C++ and C# skills", "C#", True),
        ("Shipped a React app", "React.js", True),
        ("Set up CI/CD pipelines", "CI/CD", True),
        ("Deployed on AWS Lambda", "Amazon Web Services (AWS)", True),
        ("Designed REST API endpoints", "REST APIs", True),
        ("Used Kafka", "Kubernetes", False),
    ],
)
def test_contains_keyword(text, keyword, expected):
    assert scoring.contains_keyword(text, keyword) is expected


def test_keyword_match_scores_and_dedupes():
    result = scoring.keyword_match("Python, Flask, Docker", ["Python", "Flask", "Kubernetes", "python", "AWS"])
    assert result.matched == ["Python", "Flask"]
    assert result.missing == ["Kubernetes", "AWS"]
    assert result.score == 50  # 2 of 4 unique keywords ("python" is a case-insensitive duplicate)


def test_ats_report_is_bounded_and_explained(sample_resume):
    match = scoring.keyword_match(scoring.resume_to_text(sample_resume), ["Python", "React", "Kubernetes"])
    report = scoring.ats_report(sample_resume, match)
    assert 0 <= report.score <= 100
    assert sum(c.max_points for c in report.checks) == 100
    assert {c.label for c in report.checks} >= {"Keyword coverage", "Contact details", "Quantified impact"}


def test_resume_to_text_contains_all_sections(sample_resume):
    text = scoring.resume_to_text(sample_resume)
    for expected in ("SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS", "Acme Corp"):
        assert expected in text
