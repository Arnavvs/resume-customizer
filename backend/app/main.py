"""FastAPI application: resume parsing, LLM tailoring, cover letters, and file export."""

import logging
import re
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import export, llm, parsing, scoring
from .config import get_settings
from .schemas import (
    JD_MAX_CHARS,
    JD_MIN_CHARS,
    CoverLetterRequest,
    ExportRequest,
    ParseResponse,
    Resume,
    Scores,
    TailorRequest,
    TailorResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Resume Customizer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Page-Count"],
)


# ---------------------------------------------------------------------------
# Errors: always return {"detail": "<human readable message>"}
# ---------------------------------------------------------------------------

FIELD_MESSAGES = {
    "job_description": f"The job description must be between {JD_MIN_CHARS} and {JD_MAX_CHARS:,} characters.",
    "sections": "Select at least one section to customize.",
}


@app.exception_handler(llm.LLMError)
async def llm_error_handler(_: Request, exc: llm.LLMError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    for error in exc.errors():
        field = next((str(p) for p in error.get("loc", []) if str(p) in FIELD_MESSAGES), None)
        if field:
            return JSONResponse(status_code=422, content={"detail": FIELD_MESSAGES[field]})
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse(status_code=422, content={"detail": f"Invalid request: {where} {first.get('msg', '')}".strip()})


# ---------------------------------------------------------------------------
# Simple in-memory rate limit for endpoints that spend LLM quota
# ---------------------------------------------------------------------------

_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    now, window = time.monotonic(), 3600
    hits = _hits[ip]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= settings.rate_limit_per_hour:
        raise HTTPException(429, "You've hit the hourly request limit for this demo. Please try again later.")
    hits.append(now)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": settings.gemini_model, "llm_configured": bool(settings.gemini_api_key)}



@app.post("/api/resume/parse", response_model=ParseResponse, dependencies=[Depends(rate_limit)])
async def parse_resume(file: UploadFile = File(...)) -> ParseResponse:
    filename = file.filename or "resume"
    if parsing.file_extension(filename) not in parsing.SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "Unsupported file type. Please upload a PDF or DOCX file.")

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File is too large. The maximum size is {settings.max_upload_mb:g} MB.")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")

    try:
        extracted = parsing.extract(filename, data)
    except parsing.ResumeParseError as exc:
        raise HTTPException(422, str(exc)) from exc

    resume = await llm.structure_resume(extracted.text, extracted.links)
    for item in resume.contact:  # emails, phones and bare domains become links even without a hyperlink
        item.url = export.contact_url(item)
    return ParseResponse(filename=filename, size_bytes=len(data), text=extracted.text, resume=resume)


@app.post("/api/resume/tailor", response_model=TailorResponse, dependencies=[Depends(rate_limit)])
async def tailor_resume(req: TailorRequest) -> TailorResponse:
    sections = list(dict.fromkeys(req.sections))
    output = await llm.tailor_resume(req.job_description, req.resume, sections, req.intensity, req.page_target)
    tailored = enforce_invariants(req.resume, output.resume, sections)
    tailored, pages = await fit_to_page_target(req, tailored, sections)

    keywords = req.jd_keywords or output.jd_keywords
    tailored_text = scoring.resume_to_text(tailored)
    match_before = scoring.keyword_match(req.resume_text, keywords)
    match_after = scoring.keyword_match(tailored_text, keywords)

    return TailorResponse(
        target_role=output.target_role,
        jd_keywords=keywords,
        resume=tailored,
        matched_skills=output.matched_skills,
        # Only report gaps that really are absent from the tailored resume.
        missing_keywords=[k for k in output.missing_keywords if not scoring.contains_keyword(tailored_text, k.keyword)],
        change_log=output.change_log,
        sections=sections,
        intensity=req.intensity,
        page_target=req.page_target,
        page_count=pages,
        scores=Scores(
            match_before=match_before,
            match_after=match_after,
            ats_before=scoring.ats_report(req.resume, match_before),
            ats_after=scoring.ats_report(tailored, match_after),
        ),
    )


async def fit_to_page_target(req: TailorRequest, tailored: Resume, sections: list[str]) -> tuple[Resume, int]:
    """Render the PDF; if it still overflows the requested page count even at the tightest layout,
    ask the LLM once to condense by relevance. A failed condense keeps the longer version."""
    pages = await run_in_threadpool(export.page_count, tailored, req.page_target)
    target = export.PAGE_TARGETS.get(req.page_target)
    if target is None or pages <= target:
        return tailored, pages
    try:
        condensed = await llm.condense_resume(
            req.job_description, tailored, target, f"At the tightest layout it currently runs to {pages} pages."
        )
    except llm.LLMError as exc:
        log.warning("Condense step failed, returning the uncondensed resume: %s", exc)
        return tailored, pages
    condensed = enforce_invariants(req.resume, condensed, sections)
    return condensed, await run_in_threadpool(export.page_count, condensed, req.page_target)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def enforce_invariants(original: Resume, tailored: Resume, sections: list[str]) -> Resume:
    """Guard against the LLM touching things it must not change, regardless of what it returned."""
    result = tailored.model_copy(deep=True)
    # Identity, education and misc sections are never rewritten.
    result.name, result.contact = original.name, original.contact
    result.education, result.extra_sections = original.education, original.extra_sections
    if not result.headline:
        result.headline = original.headline

    for section in ("summary", "skills", "experience", "projects"):
        if section not in sections:
            setattr(result, section, getattr(original, section))

    # Role metadata must stay factual: restore titles/companies/dates when roles line up.
    if "experience" in sections and len(result.experience) == len(original.experience):
        for new, old in zip(result.experience, original.experience):
            new.title, new.company, new.location, new.dates = old.title, old.company, old.location, old.dates
    elif "experience" in sections:
        result.experience = original.experience  # the model dropped or invented a role: fall back safely

    # Projects may be reordered or (for page limits) dropped, but never invented or renamed,
    # and their links always come from the original.
    if "projects" in sections:
        originals = {_key(p.name): p for p in original.projects}
        kept = []
        for proj in result.projects:
            source = originals.get(_key(proj.name))
            if source:
                proj.name, proj.details, proj.url = source.name, source.details, source.url
                kept.append(proj)
        result.projects = kept if kept or not original.projects else original.projects
    return result


@app.post("/api/cover-letter", dependencies=[Depends(rate_limit)])
async def cover_letter(req: CoverLetterRequest) -> StreamingResponse:
    stream = llm.stream_cover_letter(req.job_description, req.resume, req.tone)
    # Pull the first chunk before responding so that auth/quota errors become proper HTTP errors
    # instead of a 200 response that dies mid-stream.
    try:
        first = await anext(stream)
    except StopAsyncIteration:
        raise llm.LLMError("The AI returned an empty cover letter. Please try again.") from None

    async def body():
        yield first
        try:
            async for chunk in stream:
                yield chunk
        except llm.LLMError as exc:
            yield f"\n\n[Generation interrupted: {exc}]"

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-cache"})


MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


@app.post("/api/export/{fmt}")
async def export_resume(fmt: str, req: ExportRequest) -> Response:
    if fmt not in MEDIA_TYPES:
        raise HTTPException(404, "Supported export formats are pdf and docx.")
    if fmt == "pdf":
        result = await run_in_threadpool(export.to_pdf, req.resume, req.page_target)
        content, pages = result.content, result.pages
    else:
        content = await run_in_threadpool(export.to_docx, req.resume, req.page_target)
        pages = None
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", req.resume.name).strip("_") or "resume"
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}_Resume.{fmt}"'}
    if pages is not None:
        headers["X-Page-Count"] = str(pages)
    return Response(content=content, media_type=MEDIA_TYPES[fmt], headers=headers)
