"""Short-lived download links for generated files.

MCP clients (Claude, Codex, ...) work with text, so instead of pushing a PDF through the tool
result, export tools store the file here and return a URL the user can open. Files live in
memory for TTL_SECONDS; the store is per-instance and is cleared on restart, which is fine for a
"click this link now" use case and keeps the backend free of persistent user data.
"""

import secrets
import time
from dataclasses import dataclass

TTL_SECONDS = 3600
MAX_FILES = 200


@dataclass
class StoredFile:
    content: bytes
    media_type: str
    filename: str
    expires_at: float


_files: dict[str, StoredFile] = {}


def _purge() -> None:
    now = time.monotonic()
    for token in [t for t, f in _files.items() if f.expires_at < now]:
        del _files[token]
    while len(_files) >= MAX_FILES:  # oldest first (dicts keep insertion order)
        del _files[next(iter(_files))]


def store(content: bytes, media_type: str, filename: str) -> str:
    _purge()
    token = secrets.token_urlsafe(16)
    _files[token] = StoredFile(content, media_type, filename, time.monotonic() + TTL_SECONDS)
    return token


def get(token: str) -> StoredFile | None:
    _purge()
    return _files.get(token)
