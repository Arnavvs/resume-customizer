"""Thin wrapper around the Gemini API (google-genai SDK).

Resilience strategy: each request walks a chain of models (GEMINI_MODEL, then
GEMINI_FALLBACK_MODELS).
* Overload, rate-limit, deadline and timeout errors (429, 503, 504, client timeout) move straight
  to the next model: on the free tier a model that is slow or overloaded right now usually stays
  that way for a while, so waiting on it again only adds latency.
* Other transient errors (500, 502, malformed JSON, network blips) are retried once on the same
  model first.
* Bad key / bad request errors fail immediately.
Each attempt has its own timeout, so a hung model costs seconds, not minutes.

Latency: these tasks are rewriting/extraction, not deep reasoning, so the model's "thinking" is
kept low. Measured on the sample resume: tailoring ~8-11 s with low thinking vs 25-55 s default.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from . import prompts
from .config import get_settings
from .schemas import Resume, TailorOutput

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

SKIP_TO_NEXT_MODEL = {404, 429, 503, 504}
ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 1.5

# Per-attempt timeouts (seconds). The overall request can take longer if it falls back.
PARSE_TIMEOUT = 45
TAILOR_TIMEOUT = 75
COVER_LETTER_TIMEOUT = 90


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


def _thinking(model: str, budget_tokens: int) -> types.ThinkingConfig:
    """Gemini 2.x takes a token budget; Gemini 3.x takes a coarse thinking level."""
    if model.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=budget_tokens)
    return types.ThinkingConfig(thinking_level="low")


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException))


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
        if exc.code == 504:
            return LLMError("The AI service took too long to respond. Please try again.", 504)
    if _is_timeout(exc):
        return LLMError("The AI service took too long to respond. Please try again.", 504)
    return LLMError("The AI service is temporarily unavailable. Please try again shortly.", 502)


def _should_skip_model(exc: BaseException) -> bool:
    return _is_timeout(exc) or (isinstance(exc, errors.APIError) and exc.code in SKIP_TO_NEXT_MODEL)


def _is_fatal(exc: BaseException) -> bool:
    """Errors no other model or retry will fix (bad key, bad request)."""
    return isinstance(exc, errors.APIError) and exc.code in (400, 401, 403)


async def _generate_structured(
    system: str, user: str, schema: type[T], temperature: float, timeout: int, thinking_budget: int
) -> T:
    last_exc: BaseException | None = None
    for model in get_settings().model_chain:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=_thinking(model, thinking_budget),
        )
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                response = await asyncio.wait_for(
                    _client().aio.models.generate_content(model=model, contents=user, config=config), timeout
                )
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
        prompts.PARSE_SYSTEM,
        prompts.parse_user_prompt(resume_text),
        Resume,
        temperature=0.0,
        timeout=PARSE_TIMEOUT,
        thinking_budget=0,  # pure extraction
    )


INTENSITY_TEMPERATURE = {"conservative": 0.2, "balanced": 0.4, "bold": 0.7}


async def tailor_resume(job_description: str, resume: Resume, sections: list[str], intensity: str) -> TailorOutput:
    return await _generate_structured(
        prompts.TAILOR_SYSTEM,
        prompts.tailor_user_prompt(job_description, resume, sections, intensity),
        TailorOutput,
        temperature=INTENSITY_TEMPERATURE[intensity],
        timeout=TAILOR_TIMEOUT,
        thinking_budget=1024,
    )


async def stream_cover_letter(job_description: str, resume: Resume, tone: str) -> AsyncIterator[str]:
    contents = prompts.cover_letter_user_prompt(job_description, resume, tone)
    last_exc: BaseException | None = None
    for model in get_settings().model_chain:
        config = types.GenerateContentConfig(
            system_instruction=prompts.COVER_LETTER_SYSTEM,
            temperature=0.6,
            thinking_config=_thinking(model, 512),
            # A per-request HTTP timeout (rather than asyncio.timeout around the generator) so the
            # deadline never fires while we're suspended at `yield` waiting on the client.
            http_options=types.HttpOptions(timeout=COVER_LETTER_TIMEOUT * 1000),
        )
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
