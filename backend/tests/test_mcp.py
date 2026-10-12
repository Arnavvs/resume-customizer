"""MCP endpoint tests over real HTTP JSON-RPC, with the LLM layer stubbed out."""

import base64

import pytest
from fastapi.testclient import TestClient

from app import llm, main, ratelimit
from app.schemas import MissingKeyword, TailorOutput

from .test_api import JD
from .test_parsing import RESUME_LINES, make_docx

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def app_client():
    # The MCP session manager can only be started once per process, so share one app lifespan.
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def client(app_client, monkeypatch, sample_resume):
    ratelimit.reset()

    async def fake_structure(text, links):
        return sample_resume

    async def fake_tailor(jd, resume, sections, intensity, page_target="auto"):
        tailored = resume.model_copy(deep=True)
        tailored.summary = "Backend engineer building Python REST APIs with Flask and PostgreSQL."
        return TailorOutput(
            target_role="Backend Engineer",
            jd_keywords=["Python", "Flask", "Kubernetes"],
            resume=tailored,
            matched_skills=["Python"],
            missing_keywords=[MissingKeyword(keyword="Kubernetes", importance="high", suggestion="Add if used.")],
            change_log=["Rewrote summary"],
        )

    async def fake_cover_letter(jd, resume, tone):
        yield "Dear Hiring Manager, "
        yield "hello."

    monkeypatch.setattr(llm, "structure_resume", fake_structure)
    monkeypatch.setattr(llm, "tailor_resume", fake_tailor)
    monkeypatch.setattr(llm, "stream_cover_letter", fake_cover_letter)
    return app_client


def rpc(client, method, params=None, id_=1):
    res = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    assert res.status_code == 200, res.text
    return res.json()


def call(client, tool, arguments):
    return rpc(client, "tools/call", {"name": tool, "arguments": arguments})["result"]


def test_initialize_and_list_tools(client):
    init = rpc(client, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"},
    })
    assert init["result"]["serverInfo"]["name"] == "resume-customizer"
    assert "tailor_resume" in init["result"]["instructions"]

    tools = {t["name"]: t for t in rpc(client, "tools/list")["result"]["tools"]}
    assert set(tools) == {"tailor_resume", "write_cover_letter", "export_resume", "run_sample_demo"}
    assert "job_description" in tools["tailor_resume"]["inputSchema"]["properties"]
    assert tools["tailor_resume"]["outputSchema"]["properties"]["pdf_url"]


def test_tailor_from_text_returns_markdown_scores_and_working_links(client):
    result = call(client, "tailor_resume", {"job_description": JD, "resume_text": "\n".join(RESUME_LINES) * 2})
    assert not result.get("isError"), result
    data = result["structuredContent"]
    assert data["target_role"] == "Backend Engineer"
    assert data["resume_markdown"].startswith("# Priya Sharma")
    assert "[LinkedIn](https://linkedin.com/in/priya)" in data["resume_markdown"]
    assert data["missing_keywords"][0]["keyword"] == "Kubernetes"
    assert data["page_count"] == 1

    pdf = client.get(data["pdf_url"].replace("http://testserver", ""))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = client.get(data["docx_url"].replace("http://testserver", ""))
    assert docx.status_code == 200 and docx.content.startswith(b"PK")


def test_tailor_from_base64_file(client):
    encoded = base64.b64encode(make_docx(RESUME_LINES)).decode()
    result = call(client, "tailor_resume", {
        "job_description": JD, "resume_file_base64": encoded, "resume_filename": "cv.docx", "page_target": "two",
    })
    assert not result.get("isError"), result


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"job_description": "too short", "resume_text": "x" * 200}, "job_description must be"),
        ({"job_description": JD}, "Provide the resume"),
        ({"job_description": JD, "resume_file_base64": "%%%", "resume_filename": "cv.pdf"}, "not valid base64"),
        ({"job_description": JD, "resume_file_base64": "aGVsbG8=", "resume_filename": "cv.png"}, "Unsupported file type"),
    ],
)
def test_tailor_errors_are_tool_errors_with_clear_messages(client, arguments, message):
    result = call(client, "tailor_resume", arguments)
    assert result["isError"] is True
    assert message in result["content"][0]["text"]


def test_cover_letter_and_export(client, sample_resume):
    letter = call(client, "write_cover_letter", {"job_description": JD, "resume": sample_resume.model_dump()})
    assert letter["structuredContent"]["result"] == "Dear Hiring Manager, hello."

    export = call(client, "export_resume", {"resume": sample_resume.model_dump(), "format": "docx"})["structuredContent"]
    assert export["filename"] == "Priya_Sharma_Resume.docx"
    assert client.get(export["url"].replace("http://testserver", "")).status_code == 200


def test_expired_download_link(client):
    res = client.get("/api/download/not-a-real-token")
    assert res.status_code == 404
    assert "expired" in res.json()["detail"]


def test_sample_demo_runs_without_user_data(client):
    data = call(client, "run_sample_demo", {})["structuredContent"]
    assert data["scores"]["jd_keyword_match_after"] >= 0
    assert data["pdf_url"]
