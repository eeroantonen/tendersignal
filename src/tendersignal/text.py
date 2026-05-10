from __future__ import annotations

from collections.abc import Iterable
from typing import Any

LANGUAGE_PREFERENCE = ("eng", "fin", "swe", "deu", "fra", "est", "dan")


def flatten(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        parts: list[str] = []
        for language in LANGUAGE_PREFERENCE:
            if language in value:
                parts.extend(flatten(value[language]))
        if parts:
            return parts
        for nested in value.values():
            parts.extend(flatten(nested))
        return parts
    if isinstance(value, Iterable):
        parts = []
        for item in value:
            parts.extend(flatten(item))
        return parts
    return [str(value)]


def first_text(value: Any, default: str = "") -> str:
    for item in flatten(value):
        cleaned = " ".join(item.split())
        if cleaned:
            return cleaned
    return default


def join_text(value: Any, max_chars: int | None = None) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for item in flatten(value):
        cleaned = " ".join(item.split())
        if cleaned and cleaned not in seen:
            unique.append(cleaned)
            seen.add(cleaned)
    text = "\n\n".join(unique)
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
