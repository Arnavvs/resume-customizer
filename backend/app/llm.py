"""Thin wrapper around the Gemini API (google-genai SDK).

Resilience strategy: each request walks a chain of models (GEMINI_MODEL, then
GEMINI_FALLBACK_MODELS). Overload / rate-limit errors (429, 503) move straight to the next
model; transient errors (500, 502, 504, timeouts, malformed JSON) are retried once on the same
model first. Only if every model fails does the user see a (friendly) error.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from . import prompts
from .config import get_settings
from .schemas import Resume, TailorOutput

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

SKIP_TO_NEXT_MODEL = {429, 503}  # model overloaded / quota exhausted: another model may be fine
RETRY_SAME_MODEL = {500, 502, 504}
ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 1.5


class LLMError(RuntimeError):
    """An LLM failure with a message that is safe to show to end users."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@lru_cache
def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("The server is missing its GEMINI_API_KEY. Please contact the site owner.", 503)
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
    )


def _friendly_error(exc: BaseException | None) -> LLMError:
    if isinstance(exc, ValidationError):
        return LLMError("The AI returned an incomplete response. Please try again.")
    if isinstance(exc, errors.APIError):
        if exc.code == 429:
            return LLMError("The AI service is busy (rate limit reached). Please wait a minute and try again.", 429)
        if exc.code == 503:
            return LLMError("The AI service is overloaded right now. Please try again in a minute.", 503)
        if exc.code in (401, 403):
            return LLMError("The AI service rejected the server's API key. Please contact the site owner.", 503)
        if exc.code == 400:
            return LLMError("The AI service couldn't process this request. Try a shorter job description.", 502)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return LLMError("The AI service took too long to respond. Please try again.", 504)
    return LLMError("The AI service is temporarily unavailable. Please try again shortly.", 502)


def _should_skip_model(exc: BaseException) -> bool:
    return isinstance(exc, errors.APIError) and (exc.code in SKIP_TO_NEXT_MODEL or exc.code == 404)


def _is_fatal(exc: BaseException) -> bool:
    """Errors no other model or retry will fix (bad key, bad request)."""
    return isinstance(exc, errors.APIError) and exc.code in (400, 401, 403)


async def _generate_structured(system: str, user: str, schema: type[T], temperature: float) -> T:
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
    )
    last_exc: BaseException | None = None
    for model in get_settings().model_chain:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                response = await _client().aio.models.generate_content(model=model, contents=user, config=config)
                if isinstance(response.parsed, schema):
                    return response.parsed
                # Fall back to validating the raw text ourselves (e.g. if the SDK could not parse it).
                return schema.model_validate_json(response.text or "")
            except LLMError:
                raise
            except Exception as exc:
                last_exc = exc
                code = getattr(exc, "code", type(exc).__name__)
                log.warning("LLM call failed (model=%s attempt=%d error=%s): %s", model, attempt, code, exc)
                if _is_fatal(exc):
                    raise _friendly_error(exc) from exc
                if _should_skip_model(exc):
                    break
                if attempt < ATTEMPTS_PER_MODEL:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise _friendly_error(last_exc)


async def structure_resume(resume_text: str) -> Resume:
    return await _generate_structured(
        prompts.PARSE_SYSTEM, prompts.parse_user_prompt(resume_text), Resume, temperature=0.0
    )


INTENSITY_TEMPERATURE = {"conservative": 0.2, "balanced": 0.4, "bold": 0.7}


async def tailor_resume(job_description: str, resume: Resume, sections: list[str], intensity: str) -> TailorOutput:
    return await _generate_structured(
        prompts.TAILOR_SYSTEM,
        prompts.tailor_user_prompt(job_description, resume, sections, intensity),
        TailorOutput,
        temperature=INTENSITY_TEMPERATURE[intensity],
    )


async def stream_cover_letter(job_description: str, resume: Resume, tone: str) -> AsyncIterator[str]:
    config = types.GenerateContentConfig(system_instruction=prompts.COVER_LETTER_SYSTEM, temperature=0.6)
    contents = prompts.cover_letter_user_prompt(job_description, resume, tone)
    last_exc: BaseException | None = None
    for model in get_settings().model_chain:
        started = False
        try:
            stream = await _client().aio.models.generate_content_stream(model=model, contents=contents, config=config)
            async for chunk in stream:
                if chunk.text:
                    started = True
                    yield chunk.text
            return
        except LLMError:
            raise
        except Exception as exc:
            last_exc = exc
            log.warning("Cover letter stream failed (model=%s): %s", model, exc)
            # Once text has reached the user we can't transparently switch models.
            if started or _is_fatal(exc):
                raise _friendly_error(exc) from exc
    raise _friendly_error(last_exc)
