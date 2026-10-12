import pytest

from app.schemas import ContactItem, EducationItem, ExperienceItem, ExtraSection, ProjectItem, Resume, SkillGroup


@pytest.fixture
def sample_resume() -> Resume:
    return Resume(
        name="Priya Sharma",
        headline="Software Engineer",
        contact=[
            ContactItem(text="priya@example.com", url="mailto:priya@example.com"),
            ContactItem(text="+91 98765 43210", url=""),
            ContactItem(text="LinkedIn", url="https://linkedin.com/in/priya"),
            ContactItem(text="Bengaluru", url=""),
        ],
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
        projects=[
            ProjectItem(
                name="Inventory Tracker",
                details="Django, PostgreSQL",
                url="https://github.com/priya/inventory",
                bullets=["Built inventory app"],
            )
        ],
        education=[EducationItem(degree="B.Tech Computer Science", institution="IIT Delhi", dates="2017 – 2021", details="")],
        extra_sections=[ExtraSection(title="Certifications", items=["AWS Certified Cloud Practitioner"])],
    )
