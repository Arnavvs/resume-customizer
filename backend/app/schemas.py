"""Pydantic models shared by the API and the LLM.

Models used as Gemini `response_schema` deliberately have no default values: the Gemini
structured-output schema does not accept defaults, and making every field required forces
the model to emit a complete, predictable shape (empty string / empty list when absent).
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Structured resume (LLM output and API payload)
# ---------------------------------------------------------------------------


class SkillGroup(BaseModel):
    category: str = Field(description="Group name, e.g. 'Languages', 'Frameworks', 'Tools'.")
    skills: list[str]


class ExperienceItem(BaseModel):
    title: str
    company: str
    location: str = Field(description="Empty string if not given.")
    dates: str = Field(description="Exactly as written, e.g. 'Jan 2022 – Present'.")
    bullets: list[str]


class ProjectItem(BaseModel):
    name: str
    details: str = Field(description="Secondary line such as tech stack, link or dates. Empty string if none.")
    bullets: list[str]


class EducationItem(BaseModel):
    degree: str
    institution: str
    dates: str
    details: str = Field(description="GPA, honours, coursework etc. Empty string if none.")


class ExtraSection(BaseModel):
    title: str = Field(description="Section heading, e.g. 'Certifications', 'Awards', 'Languages'.")
    items: list[str]


class Resume(BaseModel):
    name: str
    headline: str = Field(description="Professional title line under the name. Empty string if none.")
    contact: list[str] = Field(description="Email, phone, location, profile URLs — one entry each.")
    summary: str = Field(description="Summary / objective paragraph. Empty string if none.")
    skills: list[SkillGroup]
    experience: list[ExperienceItem]
    projects: list[ProjectItem]
    education: list[EducationItem]
    extra_sections: list[ExtraSection]


class MissingKeyword(BaseModel):
    keyword: str
    importance: Literal["high", "medium", "low"]
    suggestion: str = Field(description="How the candidate could honestly address this gap.")


class TailorOutput(BaseModel):
    """What the tailoring prompt asks the LLM to return."""

    target_role: str = Field(description="Job title (and company, if stated) from the JD.")
    jd_keywords: list[str] = Field(
        description="10-25 most important hard skills, tools, and domain terms from the JD, canonical spelling."
    )
    resume: Resume
    matched_skills: list[str] = Field(description="JD-relevant skills the candidate demonstrably has.")
    missing_keywords: list[MissingKeyword]
    change_log: list[str] = Field(description="3-8 short notes explaining the most important edits.")


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

Section = Literal["summary", "skills", "experience", "projects"]
Intensity = Literal["conservative", "balanced", "bold"]

JD_MIN_CHARS = 100
JD_MAX_CHARS = 20_000


class ParseResponse(BaseModel):
    filename: str
    size_bytes: int
    text: str
    resume: Resume


class TailorRequest(BaseModel):
    job_description: str = Field(min_length=JD_MIN_CHARS, max_length=JD_MAX_CHARS)
    resume_text: str = Field(min_length=1, max_length=60_000)
    resume: Resume
    sections: list[Section] = Field(default=["summary", "skills", "experience", "projects"], min_length=1)
    intensity: Intensity = "balanced"
    # Keywords from an earlier version for the same JD, so scores stay comparable across versions.
    jd_keywords: list[str] | None = Field(default=None, max_length=40)


class ScoreCheck(BaseModel):
    label: str
    passed: bool
    detail: str
    points: float
    max_points: float


class AtsReport(BaseModel):
    score: int
    checks: list[ScoreCheck]


class KeywordMatch(BaseModel):
    score: int
    matched: list[str]
    missing: list[str]


class Scores(BaseModel):
    match_before: KeywordMatch
    match_after: KeywordMatch
    ats_before: AtsReport
    ats_after: AtsReport


class TailorResponse(BaseModel):
    target_role: str
    jd_keywords: list[str]
    resume: Resume
    matched_skills: list[str]
    missing_keywords: list[MissingKeyword]
    change_log: list[str]
    sections: list[Section]
    intensity: Intensity
    scores: Scores


class CoverLetterRequest(BaseModel):
    job_description: str = Field(min_length=JD_MIN_CHARS, max_length=JD_MAX_CHARS)
    resume: Resume
    tone: Literal["professional", "enthusiastic", "concise"] = "professional"


class ExportRequest(BaseModel):
    resume: Resume
