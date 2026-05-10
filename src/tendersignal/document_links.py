from __future__ import annotations

import re
from typing import Any

from tendersignal.text import flatten

URL_PATTERN = re.compile(r"https?://[^\s,;)\]}>\"]+")


def collect_urls(*values: Any) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        for text in flatten(value):
            for match in URL_PATTERN.findall(text):
                url = match.rstrip(".")
                if url not in seen:
                    urls.append(url)
                    seen.add(url)
    return urls
