"""Remote MCP server, so AI agents (Claude, Codex, Cursor, ...) can use the app directly.

Mounted on the FastAPI app at /mcp (Streamable HTTP, stateless, no auth). Connect with e.g.

    claude mcp add --transport http resume-customizer https://<api-host>/mcp
    codex mcp add resume-customizer --url https://<api-host>/mcp

The tools call the same service layer as the REST API, so behaviour, guardrails (truthfulness
invariants, page fitting) and rate limits are identical to the web app.
"""

import base64
import binascii
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import downloads, llm, parsing, ratelimit, scoring, service
from .config import get_settings
from .schemas import JD_MAX_CHARS, JD_MIN_CHARS, Intensity, PageTarget, Resume, Section, TailorRequest

SAMPLES = Path(__file__).parent / "samples"
ALL_SECTIONS: list[Section] = ["summary", "skills", "experience", "projects"]

INSTRUCTIONS = """Resume Customizer tailors a candidate's resume to a job description with Gemini,
without inventing experience, and scores the result.

Typical flow:
1. Call `tailor_resume` with the job description and the resume. Pass the resume either as
   plain text (`resume_text`, e.g. text you read from the user's file) or as the original file
   (`resume_file_base64` + `resume_filename`, PDF or DOCX). The file route keeps hyperlinks.
2. Show the user the tailored resume (`resume_markdown`), the before/after scores and the
   `missing_keywords` suggestions, and give them the `pdf_url` / `docx_url` download links
   (valid for about an hour).
3. Optionally call `write_cover_letter`, or `export_resume` after editing the structured resume.

To check the service end to end without any user data, call `run_sample_demo`.
Calls take 10-60 seconds because they run an LLM; the first call after idle may add ~50 s while
the free-tier server wakes up."""

mcp = MCPServer(
    name="resume-customizer",
    title="Resume Customizer",
    instructions=INSTRUCTIONS,
    website_url="https://resume-customizer-gamma-topaz.vercel.app",
    version="1.0.0",
)

LLM_TOOL = ToolAnnotations(readOnlyHint=True, openWorldHint=True, idempotentHint=False)


# ---------------------------------------------------------------------------
# Result models (become the tools' structured output)
# ---------------------------------------------------------------------------


class ScoreSummary(BaseModel):
    jd_keyword_match_before: int = Field(description="% of the JD's key terms found in the original resume")
    jd_keyword_match_after: int
    ats_score_before: int = Field(description="0-100 ATS readiness checklist score")
    ats_score_after: int


class Gap(BaseModel):
    keyword: str
    importance: str
    suggestion: str


class TailorResult(BaseModel):
    target_role: str
    page_count: int = Field(description="Pages the PDF takes")
    scores: ScoreSummary
    change_log: list[str] = Field(description="What was changed and why")
    missing_keywords: list[Gap] = Field(description="JD requirements the resume doesn't show (not added — suggestions)")
    resume_markdown: str = Field(description="The tailored resume, ready to show the user")
    pdf_url: str = Field(description="Download link for the tailored PDF (expires in ~1 hour)")
    docx_url: str = Field(description="Download link for the tailored DOCX (expires in ~1 hour)")
    resume: Resume = Field(description="Structured tailored resume; pass to export_resume/write_cover_letter")


class ExportResult(BaseModel):
    url: str = Field(description="Download link (expires in ~1 hour)")
    filename: str
    page_count: int | None = Field(description="Pages, for PDF exports")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_rate_limit(ctx: Context) -> None:
    try:
        ratelimit.check("mcp:" + ratelimit.client_ip(ctx.request_context.request))
    except ratelimit.RateLimitExceeded as exc:
        raise ToolError(str(exc)) from exc


def _base_url(ctx: Context) -> str:
    configured = get_settings().public_api_url
    if configured:
        return configured
    request = ctx.request_context.request
    return str(request.base_url).rstrip("/") if request is not None else ""


async def _download_link(ctx: Context, resume: Resume, fmt: str, page_target: str) -> tuple[str, str, int | None]:
    content, pages = await service.render(resume, fmt, page_target)
    filename = service.file_name(resume, fmt)
    token = downloads.store(content, service.MEDIA_TYPES[fmt], filename)
    return f"{_base_url(ctx)}/api/download/{token}", filename, pages


def _check_jd(job_description: str) -> str:
    jd = job_description.strip()
    if not JD_MIN_CHARS <= len(jd) <= JD_MAX_CHARS:
        raise ToolError(f"job_description must be {JD_MIN_CHARS}-{JD_MAX_CHARS:,} characters (got {len(jd)}).")
    return jd


async def _load_resume(resume_text: str, resume_file_base64: str, resume_filename: str):
    try:
        if resume_file_base64:
            try:
                data = base64.b64decode(resume_file_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ToolError("resume_file_base64 is not valid base64.") from exc
            if len(data) > get_settings().max_upload_bytes:
                raise ToolError(f"The file is larger than {get_settings().max_upload_mb:g} MB.")
            return await service.parse_file(resume_filename or "resume.pdf", data)
        if resume_text.strip():
            return await service.parse_text(resume_text)
    except parsing.ResumeParseError as exc:
        raise ToolError(str(exc)) from exc
    except llm.LLMError as exc:
        raise ToolError(str(exc)) from exc
    raise ToolError("Provide the resume as resume_text or as resume_file_base64 + resume_filename.")


async def _tailor(ctx, jd, parsed, page_target, intensity, sections) -> TailorResult:
    try:
        result = await service.tailor(
            TailorRequest(
                job_description=jd,
                resume_text=parsed.text,
                resume=parsed.resume,
                sections=sections or ALL_SECTIONS,
                intensity=intensity,
                page_target=page_target,
            )
        )
    except llm.LLMError as exc:
        raise ToolError(str(exc)) from exc
    pdf_url, _, _ = await _download_link(ctx, result.resume, "pdf", page_target)
    docx_url, _, _ = await _download_link(ctx, result.resume, "docx", page_target)
    s = result.scores
    return TailorResult(
        target_role=result.target_role,
        page_count=result.page_count,
        scores=ScoreSummary(
            jd_keyword_match_before=s.match_before.score,
            jd_keyword_match_after=s.match_after.score,
            ats_score_before=s.ats_before.score,
            ats_score_after=s.ats_after.score,
        ),
        change_log=result.change_log,
        missing_keywords=[Gap(**k.model_dump()) for k in result.missing_keywords],
        resume_markdown=scoring.resume_to_markdown(result.resume),
        pdf_url=pdf_url,
        docx_url=docx_url,
        resume=result.resume,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(title="Tailor a resume to a job description", annotations=LLM_TOOL)
async def tailor_resume(
    ctx: Context,
    job_description: str = Field(description="Full job posting text (100-20,000 characters)"),
    resume_text: str = Field(default="", description="Resume as plain text. Use this OR the file fields."),
    resume_file_base64: str = Field(default="", description="Original resume file (PDF/DOCX), base64-encoded"),
    resume_filename: str = Field(default="", description="File name incl. extension, e.g. 'cv.pdf'"),
    page_target: PageTarget = Field(default="one", description="'one' page, 'two' pages, or 'auto' (original length)"),
    intensity: Intensity = Field(default="balanced", description="conservative | balanced | bold rewriting"),
    sections: list[Section] = Field(default=ALL_SECTIONS, description="Sections the AI may rewrite"),
) -> TailorResult:
    """Tailor a resume to a job description: rewrites the summary, reorders/rephrases bullets with
    the JD's keywords (never inventing experience), fits it to 1 or 2 pages, scores keyword match
    and ATS readiness before/after, lists honest gap suggestions, and returns PDF/DOCX links."""
    _check_rate_limit(ctx)
    jd = _check_jd(job_description)
    parsed = await _load_resume(resume_text, resume_file_base64, resume_filename)
    return await _tailor(ctx, jd, parsed, page_target, intensity, sections)


@mcp.tool(title="Write a cover letter", annotations=LLM_TOOL)
async def write_cover_letter(
    ctx: Context,
    job_description: str = Field(description="Full job posting text"),
    resume: Resume | None = Field(default=None, description="Structured resume, e.g. from tailor_resume"),
    resume_text: str = Field(default="", description="Or the resume as plain text"),
    tone: Literal["professional", "enthusiastic", "concise"] = "professional",
) -> str:
    """Write a 220-320 word cover letter grounded only in facts from the resume."""
    _check_rate_limit(ctx)
    jd = _check_jd(job_description)
    if resume is None:
        resume = (await _load_resume(resume_text, "", "")).resume
    try:
        return await service.cover_letter_text(jd, resume, tone)
    except llm.LLMError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="Export a resume to PDF or DOCX",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False, idempotentHint=True),
)
async def export_resume(
    ctx: Context,
    resume: Resume = Field(description="Structured resume (the `resume` field returned by tailor_resume)"),
    format: Literal["pdf", "docx"] = "pdf",
    page_target: PageTarget = "auto",
) -> ExportResult:
    """Render a structured resume to an ATS-friendly PDF or DOCX (clickable links, fitted to the
    page target) and return a download link. No LLM call; use after editing the resume."""
    url, filename, pages = await _download_link(ctx, resume, format, page_target)
    return ExportResult(url=url, filename=filename, page_count=pages)


@mcp.tool(title="Run the sample demo", annotations=LLM_TOOL)
async def run_sample_demo(
    ctx: Context,
    page_target: PageTarget = "one",
) -> TailorResult:
    """End-to-end check with bundled sample data (a backend-engineer JD and a sample DOCX resume),
    for reviewers who want to see the service work without supplying a resume."""
    _check_rate_limit(ctx)
    jd = (SAMPLES / "job_description.txt").read_text(encoding="utf-8")
    try:
        parsed = await service.parse_file("sample_resume.docx", (SAMPLES / "sample_resume.docx").read_bytes())
    except llm.LLMError as exc:
        raise ToolError(str(exc)) from exc
    return await _tailor(ctx, jd, parsed, page_target, "balanced", ALL_SECTIONS)
