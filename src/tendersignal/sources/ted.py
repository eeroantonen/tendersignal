from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from tendersignal.config import (
    BUILDING_TECH_CPV_QUERY,
    CACHE_DIR,
    COMPETITION_NOTICE_TYPES,
    DEFAULT_COUNTRIES,
    TED_FIELDS,
    TED_NOTICE_URL,
    TED_SEARCH_URL,
)
from tendersignal.document_links import collect_urls
from tendersignal.models import Notice
from tendersignal.text import first_text, join_text, unique_strings


class TedApiError(RuntimeError):
    """Raised when TED cannot be reached or returns an unusable response."""


def build_query(
    published_after: date,
    published_before: date,
    countries: tuple[str, ...] = DEFAULT_COUNTRIES,
) -> str:
    notice_types = " ".join(COMPETITION_NOTICE_TYPES)
    country_clause = " ".join(countries)
    start = published_after.strftime("%Y%m%d")
    end = published_before.strftime("%Y%m%d")
    return (
        f"publication-date = ({start} <> {end}) "
        f"AND notice-type IN ({notice_types}) "
        f"AND buyer-country IN ({country_clause}) "
        f"AND ({BUILDING_TECH_CPV_QUERY})"
    )


def fetch_ted_notices(
    days_back: int = 21,
    limit: int = 100,
    countries: tuple[str, ...] = DEFAULT_COUNTRIES,
    timeout_seconds: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    today = date.today()
    return fetch_ted_notices_for_period(
        published_after=today - timedelta(days=days_back),
        published_before=today,
        limit=limit,
        countries=countries,
        timeout_seconds=timeout_seconds,
    )


def fetch_ted_notices_for_period(
    published_after: date,
    published_before: date,
    limit: int = 100,
    countries: tuple[str, ...] = DEFAULT_COUNTRIES,
    timeout_seconds: int = 30,
    page_size: int = 250,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query = build_query(published_after, published_before, countries)
    target = max(1, limit)
    page_size = min(page_size, 250, target)
    all_notices: list[dict[str, Any]] = []
    total_notice_count = None
    timed_out = False
    page = 1
    while len(all_notices) < target:
        current_limit = min(page_size, target - len(all_notices))
        data = search_ted_page(query=query, page=page, limit=current_limit, timeout_seconds=timeout_seconds)
        notices = data["notices"]
        all_notices.extend(notices)
        total_notice_count = data.get("totalNoticeCount", total_notice_count)
        timed_out = bool(data.get("timedOut", False)) or timed_out
        if not notices or len(notices) < current_limit:
            break
        if total_notice_count is not None and len(all_notices) >= int(total_notice_count):
            break
        page += 1
    metadata = {
        "query": query,
        "total_notice_count": total_notice_count,
        "timed_out": timed_out,
        "limit": limit,
        "countries": list(countries),
        "published_after": published_after.isoformat(),
        "published_before": published_before.isoformat(),
        "pages_fetched": page,
        "result_count": len(all_notices),
    }
    return all_notices, metadata


def search_ted_page(query: str, page: int, limit: int, timeout_seconds: int) -> dict[str, Any]:
    payload = {
        "query": query,
        "fields": TED_FIELDS,
        "page": page,
        "limit": limit,
        "scope": "ALL",
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }
    try:
        response = requests.post(TED_SEARCH_URL, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TedApiError(f"TED Search API request failed: {exc}") from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise TedApiError("TED Search API returned non-JSON data") from exc

    if "notices" not in data or not isinstance(data["notices"], list):
        raise TedApiError(f"TED Search API returned unexpected payload keys: {sorted(data.keys())}")
    return data


def write_cache(notices: list[dict[str, Any]], metadata: dict[str, Any], cache_dir: Path = CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "ted_notices_sample.json"
    payload = {"source": "TED Search API", "metadata": metadata, "notices": notices}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cache(path: Path = CACHE_DIR / "ted_notices_sample.json") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"No cached TED data found at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("notices", []), payload.get("metadata", {})


def normalize_notice(raw: dict[str, Any]) -> Notice:
    publication_number = first_text(raw.get("publication-number"), "unknown")
    title = first_text(raw.get("notice-title")) or first_text(raw.get("title-proc")) or first_text(raw.get("title-lot"))
    buyer = first_text(raw.get("buyer-name"), "Unknown buyer")
    country = first_text(raw.get("buyer-country"), "Unknown country")
    region_city = ", ".join(unique_strings(raw.get("place-of-performance", [])))
    deadline = first_text(raw.get("deadline-receipt-tender-date-lot")) or first_text(raw.get("deadline"))
    cpv_codes = unique_strings(raw.get("classification-cpv", []))
    description = join_text(raw.get("description-proc")) or join_text(raw.get("description-lot"))
    links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
    html_links = links.get("html") if isinstance(links.get("html"), dict) else {}
    pdf_links = links.get("pdf") if isinstance(links.get("pdf"), dict) else {}
    xml_links = links.get("xml") if isinstance(links.get("xml"), dict) else {}
    source_url = html_links.get("ENG") or first_text(html_links) or TED_NOTICE_URL.format(publication_number=publication_number)
    document_links = collect_urls(
        source_url,
        xml_links.get("MUL"),
        pdf_links.get("ENG"),
        raw.get("document-url-lot"),
        raw.get("document-url-part"),
        raw.get("document-restricted-url-lot"),
        raw.get("document-restricted-url-part"),
        raw.get("buyer-profile"),
        raw.get("buyer-internet-address"),
        raw.get("contract-url"),
        pdf_links,
        xml_links,
    )

    return Notice(
        publication_number=publication_number,
        title=title or "Untitled notice",
        buyer=buyer,
        country=country,
        region_city=region_city,
        deadline=deadline,
        source_url=source_url,
        cpv_codes=cpv_codes,
        document_links=document_links,
        raw_description=description,
        publication_date=normalize_publication_date(raw.get("publication-date")),
        notice_type=first_text(raw.get("notice-type")),
        source_name="TED Search API",
        raw_notice=raw,
    )


def normalize_publication_date(value: Any) -> str:
    text = first_text(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text
