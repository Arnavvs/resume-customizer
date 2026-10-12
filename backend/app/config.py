"""Runtime configuration, read once from environment variables (and a local .env file)."""

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    # Tried in order when the primary model is overloaded or rate-limited.
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: _csv(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-2.5-flash"))
    )
    llm_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT_SECONDS", "120")))
    allowed_origins: list[str] = field(
        default_factory=lambda: _csv(os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
    )
    # Optional regex so Vercel preview deployments (random subdomains) can call the API too.
    allowed_origin_regex: str | None = field(default_factory=lambda: os.getenv("ALLOWED_ORIGIN_REGEX") or None)
    max_upload_mb: float = field(default_factory=lambda: float(os.getenv("MAX_UPLOAD_MB", "5")))
    rate_limit_per_hour: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_HOUR", "60")))

    @property
    def model_chain(self) -> list[str]:
        return list(dict.fromkeys([self.gemini_model, *self.gemini_fallback_models]))

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
