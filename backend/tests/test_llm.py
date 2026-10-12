"""Model fallback / retry behaviour, using a fake Gemini client."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from app import llm
from app.config import Settings


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "boom", "status": "X"}})


class FakeModels:
    def __init__(self, outcomes: dict[str, list]):
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(parsed=outcome, text=outcome.model_dump_json())


@pytest.fixture
def fake(monkeypatch):
    def install(outcomes):
        models = FakeModels(outcomes)
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
        monkeypatch.setattr(
            llm, "get_settings",
            lambda: Settings(gemini_api_key="k", gemini_model="primary", gemini_fallback_models=["backup"]),
        )
        monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
        return models
    return install


def test_overloaded_primary_falls_back_immediately(fake, sample_resume):
    models = fake({"primary": [api_error(503)], "backup": [sample_resume]})
    result = asyncio.run(llm.structure_resume("text", []))
    assert result == sample_resume
    assert models.calls == ["primary", "backup"]


def test_transient_error_retries_same_model(fake, sample_resume):
    models = fake({"primary": [api_error(500), sample_resume], "backup": []})
    asyncio.run(llm.structure_resume("text", []))
    assert models.calls == ["primary", "primary"]


def test_timeout_skips_to_next_model(fake, sample_resume):
    models = fake({"primary": [TimeoutError()], "backup": [sample_resume]})
    asyncio.run(llm.structure_resume("text", []))
    assert models.calls == ["primary", "backup"]


def test_bad_api_key_fails_fast_with_friendly_message(fake):
    models = fake({"primary": [api_error(403)], "backup": []})
    with pytest.raises(llm.LLMError, match="API key"):
        asyncio.run(llm.structure_resume("text", []))
    assert models.calls == ["primary"]


def test_all_models_exhausted(fake):
    fake({"primary": [api_error(429)], "backup": [api_error(429)]})
    with pytest.raises(llm.LLMError) as info:
        asyncio.run(llm.structure_resume("text", []))
    assert info.value.status_code == 429
