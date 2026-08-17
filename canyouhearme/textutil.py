from __future__ import annotations

import hashlib


def expand(text: str, shortcuts: dict[str, str]) -> str:
    raw = text.strip()
    if not raw:
        return ""
    lower = raw.lower()
    mapped = shortcuts.get(raw) or shortcuts.get(lower)
    return (mapped or raw).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def char_count(text: str) -> int:
    return len(text)
