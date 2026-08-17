from __future__ import annotations

from canyouhearme.textutil import char_count


def is_corpus_line(text: str, phrases: list[str], shortcut_values: list[str]) -> bool:
    return text in phrases or text in shortcut_values


def should_keep_audio(
    text: str,
    *,
    phrases: list[str],
    shortcut_values: list[str],
    speak_count: int,
    immediate_max_chars: int,
    background_hits: int,
) -> bool:
    if is_corpus_line(text, phrases, shortcut_values):
        return True
    if char_count(text) < immediate_max_chars:
        return True
    return speak_count >= background_hits
