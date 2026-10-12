"""FastAPI application: REST API for the web app, plus the MCP endpoint for AI agents."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from . import downloads, llm, parsing, ratelimit, service
from .config import get_settings
from .mcp_server import mcp
from .schemas import (
    JD_MAX_CHARS,
    JD_MIN_CHARS,
    CoverLetterRequest,
    ExportRequest,
    ParseResponse,
    TailorRequest,
    TailorResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

# Streamable HTTP MCP endpoint at /mcp. Stateless + JSON responses: every tool call is a single
# request/response, which works behind proxies and on a free instance that may restart. DNS
# rebinding protection targets servers on a user's own machine; this one is public and sends no
# credentials, so it is off unless MCP_ALLOWED_HOSTS pins the Host header.
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(settings.mcp_allowed_hosts),
        allowed_hosts=settings.mcp_allowed_hosts,
    ),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Resume Customizer API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Page-Count"],
)
app.router.routes.extend(mcp_app.routes)


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


@app.exception_handler(parsing.ResumeParseError)
async def parse_error_handler(_: Request, exc: parsing.ResumeParseError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    for error in exc.errors():
        field = next((str(p) for p in error.get("loc", []) if str(p) in FIELD_MESSAGES), None)
        if field:
            return JSONResponse(status_code=422, content={"detail": FIELD_MESSAGES[field]})
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse(status_code=422, content={"detail": f"Invalid request: {where} {first.get('msg', '')}".strip()})


def rate_limit(request: Request) -> None:
    try:
        ratelimit.check(ratelimit.client_ip(request))
    except ratelimit.RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc


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
    return await service.parse_file(filename, data)


class ParseTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=60_000)


@app.post("/api/resume/parse-text", response_model=ParseResponse, dependencies=[Depends(rate_limit)])
async def parse_resume_text(req: ParseTextRequest) -> ParseResponse:
    return await service.parse_text(req.text)


@app.post("/api/resume/tailor", response_model=TailorResponse, dependencies=[Depends(rate_limit)])
async def tailor_resume(req: TailorRequest) -> TailorResponse:
    return await service.tailor(req)


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


@app.post("/api/export/{fmt}")
async def export_resume(fmt: str, req: ExportRequest) -> Response:
    if fmt not in service.MEDIA_TYPES:
        raise HTTPException(404, "Supported export formats are pdf and docx.")
    content, pages = await service.render(req.resume, fmt, req.page_target)
    headers = {"Content-Disposition": f'attachment; filename="{service.file_name(req.resume, fmt)}"'}
    if pages is not None:
        headers["X-Page-Count"] = str(pages)
    return Response(content=content, media_type=service.MEDIA_TYPES[fmt], headers=headers)


@app.get("/api/download/{token}")
async def download(token: str) -> Response:
    """Short-lived links handed out by the MCP export tools."""
    stored = downloads.get(token)
    if stored is None:
        raise HTTPException(404, "This download link has expired. Ask your assistant to export the resume again.")
    return Response(
        content=stored.content,
        media_type=stored.media_type,
        headers={"Content-Disposition": f'attachment; filename="{stored.filename}"'},
    )
