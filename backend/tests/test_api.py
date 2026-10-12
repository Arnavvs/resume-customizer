"""API tests with the LLM layer stubbed out, so they run offline and deterministically."""

import pytest
from fastapi.testclient import TestClient

from app import llm, main
from app.schemas import MissingKeyword, TailorOutput

from .test_parsing import RESUME_LINES, make_docx

JD = (
    "We are hiring a Backend Engineer to build Python REST APIs with FastAPI and PostgreSQL. "
    "Experience with Docker, Kubernetes and CI/CD pipelines is required. React is a plus."
)


@pytest.fixture
def client(monkeypatch, sample_resume):
    main._hits.clear()

    async def fake_structure(text, links):
        return sample_resume

    async def fake_tailor(jd, resume, sections, intensity, page_target="auto"):
        tailored = resume.model_copy(deep=True)
        tailored.summary = "Backend engineer building Python REST APIs with Flask, Docker and PostgreSQL."
        tailored.name = "Someone Else"  # must be reverted by the invariants guard
        tailored.experience[0].company = "Invented Inc"  # must be reverted too
        return TailorOutput(
            target_role="Backend Engineer",
            jd_keywords=["Python", "REST APIs", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
            resume=tailored,
            matched_skills=["Python", "PostgreSQL", "Docker"],
            missing_keywords=[
                MissingKeyword(keyword="Kubernetes", importance="high", suggestion="Add if used."),
                MissingKeyword(keyword="Docker", importance="low", suggestion="Already present."),
            ],
            change_log=["Rewrote summary for backend focus"],
        )

    monkeypatch.setattr(llm, "structure_resume", fake_structure)
    monkeypatch.setattr(llm, "tailor_resume", fake_tailor)
    return TestClient(main.app)


def test_parse_docx(client):
    res = client.post("/api/resume/parse", files={"file": ("cv.docx", make_docx(RESUME_LINES), "application/octet-stream")})
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "cv.docx"
    assert body["size_bytes"] > 0
    assert "Acme Corp" in body["text"]


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [("cv.png", b"\x89PNG", 415), ("cv.pdf", b"", 400), ("cv.pdf", b"hello world", 422)],
)
def test_parse_rejects_bad_uploads(client, name, data, status):
    res = client.post("/api/resume/parse", files={"file": (name, data, "application/octet-stream")})
    assert res.status_code == status
    assert res.json()["detail"]


def test_parse_rejects_large_files(client):
    big = b"%PDF" + b"0" * (main.settings.max_upload_bytes + 10)
    res = client.post("/api/resume/parse", files={"file": ("cv.pdf", big, "application/pdf")})
    assert res.status_code == 413
    assert "too large" in res.json()["detail"]


def test_tailor_enforces_invariants_and_scores(client, sample_resume):
    res = client.post(
        "/api/resume/tailor",
        json={"job_description": JD, "resume_text": "Python Flask", "resume": sample_resume.model_dump(),
              "sections": ["summary", "experience"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resume"]["name"] == "Priya Sharma"
    assert body["resume"]["experience"][0]["company"] == "Acme Corp"
    assert body["resume"]["summary"].startswith("Backend engineer")
    # Docker is in the tailored resume, so it must not be reported as missing.
    assert [k["keyword"] for k in body["missing_keywords"]] == ["Kubernetes"]
    scores = body["scores"]
    assert scores["match_after"]["score"] > scores["match_before"]["score"]


def test_tailor_validates_short_jd(client, sample_resume):
    res = client.post(
        "/api/resume/tailor",
        json={"job_description": "too short", "resume_text": "x", "resume": sample_resume.model_dump()},
    )
    assert res.status_code == 422
    assert "job description" in res.json()["detail"].lower()


def test_llm_errors_are_user_friendly(client, monkeypatch, sample_resume):
    async def boom(*_):
        raise llm.LLMError("The AI service is busy (rate limit reached).", 429)

    monkeypatch.setattr(llm, "tailor_resume", boom)
    res = client.post(
        "/api/resume/tailor",
        json={"job_description": JD, "resume_text": "x", "resume": sample_resume.model_dump()},
    )
    assert res.status_code == 429
    assert "busy" in res.json()["detail"]


@pytest.mark.parametrize(("fmt", "magic"), [("pdf", b"%PDF"), ("docx", b"PK")])
def test_export(client, sample_resume, fmt, magic):
    res = client.post(f"/api/export/{fmt}", json={"resume": sample_resume.model_dump()})
    assert res.status_code == 200
    assert res.content.startswith(magic)
    assert "Priya_Sharma_Resume" in res.headers["content-disposition"]
