import pytest

from app.schemas import EducationItem, ExperienceItem, ExtraSection, ProjectItem, Resume, SkillGroup


@pytest.fixture
def sample_resume() -> Resume:
    return Resume(
        name="Priya Sharma",
        headline="Software Engineer",
        contact=["priya@example.com", "+91 98765 43210", "linkedin.com/in/priya"],
        summary="Software engineer with 3 years of experience building web applications and REST services.",
        skills=[
            SkillGroup(category="Languages", skills=["Python", "JavaScript", "SQL"]),
            SkillGroup(category="Frameworks", skills=["Flask", "React", "Django"]),
            SkillGroup(category="Tools", skills=["Git", "Docker", "PostgreSQL"]),
        ],
        experience=[
            ExperienceItem(
                title="Software Engineer",
                company="Acme Corp",
                location="Bengaluru",
                dates="Jan 2022 – Present",
                bullets=[
                    "Built REST services in Flask serving 2M requests per day",
                    "Reduced page load time by 40% by optimizing React bundle size",
                    "Mentored 3 interns on code review practices",
                ],
            )
        ],
        projects=[ProjectItem(name="Inventory Tracker", details="Django, PostgreSQL", bullets=["Built inventory app"])],
        education=[EducationItem(degree="B.Tech Computer Science", institution="IIT Delhi", dates="2017 – 2021", details="")],
        extra_sections=[ExtraSection(title="Certifications", items=["AWS Certified Cloud Practitioner"])],
    )
