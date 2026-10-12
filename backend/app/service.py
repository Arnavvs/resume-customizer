"""Core use cases, shared by the REST API (main.py) and the MCP server (mcp_server.py)."""

import logging
import re

from starlette.concurrency import run_in_threadpool

from . import export, llm, parsing, scoring
from .schemas import ParseResponse, Resume, Scores, TailorRequest, TailorResponse

log = logging.getLogger(__name__)

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


async def parse_file(filename: str, data: bytes) -> ParseResponse:
    """Raises parsing.ResumeParseError for unreadable files and llm.LLMError for AI failures."""
    extracted = parsing.extract(filename, data)
    resume = await structure(extracted.text, extracted.links)
    return ParseResponse(filename=filename, size_bytes=len(data), text=extracted.text, resume=resume)


async def parse_text(text: str) -> ParseResponse:
    """Structure resume text that was pasted (or read from a file by an AI agent)."""
    text = parsing.normalize_text(text)
    if len(text) < parsing.MIN_TEXT_CHARS:
        raise parsing.ResumeParseError("The resume text is too short to be a resume.")
    resume = await structure(text, [])
    return ParseResponse(filename="resume.txt", size_bytes=len(text.encode()), text=text, resume=resume)


async def structure(text: str, links: list[parsing.Link]) -> Resume:
    resume = await llm.structure_resume(text, links)
    for item in resume.contact:  # emails, phones and bare domains become links even without a hyperlink
        item.url = export.contact_url(item)
    return resume


# ---------------------------------------------------------------------------
# Tailoring
# ---------------------------------------------------------------------------


async def tailor(req: TailorRequest) -> TailorResponse:
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


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def file_name(resume: Resume, fmt: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", resume.name).strip("_") or "resume"
    return f"{safe}_Resume.{fmt}"


async def render(resume: Resume, fmt: str, page_target: str) -> tuple[bytes, int | None]:
    """Returns (file bytes, page count — PDF only)."""
    if fmt == "pdf":
        result = await run_in_threadpool(export.to_pdf, resume, page_target)
        return result.content, result.pages
    return await run_in_threadpool(export.to_docx, resume, page_target), None


async def cover_letter_text(job_description: str, resume: Resume, tone: str) -> str:
    chunks = [chunk async for chunk in llm.stream_cover_letter(job_description, resume, tone)]
    return "".join(chunks).strip()
