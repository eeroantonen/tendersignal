from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from tendersignal.config import (
    CACHE_DIR,
    HILMA_AVP_BASE_URL,
    HILMA_AVP_SEARCH_ENDPOINT,
    HILMA_AVP_SUBSCRIPTION_KEY,
    HILMA_DEVELOPER_PORTAL_URL,
)
from tendersignal.document_links import collect_urls
from tendersignal.models import Notice
from tendersignal.text import first_text, join_text, unique_strings


class HilmaApiConfigurationError(RuntimeError):
    """Raised when the official Hilma AVP API is not configured."""


class HilmaApiError(RuntimeError):
    """Raised when Hilma AVP returns an unusable response."""


@dataclass(frozen=True)
class HilmaClient:
    """Small official-Hilma API client.

    Hilma AVP-Read is free/open data but requires self-registration and an
    `Ocp-Apim-Subscription-Key` header. Endpoint details are held in config so
    the app fails clearly until a real registered key and base URL are supplied.
    """

    base_url: str = HILMA_AVP_BASE_URL
    subscription_key: str = HILMA_AVP_SUBSCRIPTION_KEY
    search_endpoint: str = HILMA_AVP_SEARCH_ENDPOINT
    timeout_seconds: int = 45
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0

    def _headers(self) -> dict[str, str]:
        subscription_key = self.subscription_key or os.environ.get("HILMA_AVP_SUBSCRIPTION_KEY", "")
        if not subscription_key:
            raise HilmaApiConfigurationError(
                "Hilma AVP-Read requires self-registration and HILMA_AVP_SUBSCRIPTION_KEY. "
                f"Register at {HILMA_DEVELOPER_PORTAL_URL}; no Hilma notices were fabricated."
            )
        return {
            "Ocp-Apim-Subscription-Key": subscription_key,
            "Content-Type": "application/json",
        }

    def search_notices(self, payload: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
        headers = self._headers()
        endpoint = endpoint or self.search_endpoint
        if not endpoint:
            raise HilmaApiConfigurationError(
                "HILMA_AVP_SEARCH_ENDPOINT is missing. Sign in to the Hilma developer portal API details "
                "for AVP-Read/Search Notices and set the exact search endpoint path. No Hilma notices were fabricated."
            )
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        last_error: requests.RequestException | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise HilmaApiError(f"Hilma AVP search failed after {self.max_retries} attempts: {exc}") from exc
                time.sleep(self.retry_backoff_seconds * attempt)
        else:
            raise HilmaApiError(f"Hilma AVP search failed: {last_error}")
        try:
            return response.json()
        except ValueError as exc:
            raise HilmaApiError("Hilma AVP returned non-JSON data") from exc


def build_hilma_search_payload(
    days_back: int = 21,
    limit: int = 100,
    skip: int = 0,
    published_after: date | None = None,
    published_before: date | None = None,
    include_expired: bool = False,
) -> dict[str, Any]:
    """Build an Azure Search style query for building/technical notices.

    The query stays broad and conservative, then the deterministic classifier
    scores the resulting source fields.
    """

    start = published_after or (date.today() - timedelta(days=days_back))
    end = published_before
    today = date.today().isoformat()
    notice_type_filter = " or ".join(
        f"type eq '{notice_type}'"
        for notice_type in ("16", "17", "18", "19", "20", "21", "22", "23", "24", "E1", "E3")
    )
    return {
        "search": "rakennus sähkö LVI ilmanvaihto putki construction electrical HVAC plumbing",
        "top": min(limit, 100),
        "skip": skip,
        "count": True,
        "filter": hilma_filter(start, end, include_expired, today, notice_type_filter),
        "orderby": "datePublished desc",
    }


def fetch_hilma_notices(days_back: int = 21, limit: int = 100, client: HilmaClient | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return fetch_hilma_notices_for_period(
        published_after=date.today() - timedelta(days=days_back),
        published_before=None,
        limit=limit,
        include_expired=False,
        client=client,
    )


def fetch_hilma_notices_for_period(
    published_after: date,
    published_before: date | None,
    limit: int = 100,
    include_expired: bool = False,
    client: HilmaClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = client or HilmaClient()
    target = max(1, limit)
    all_notices: list[dict[str, Any]] = []
    total_count = None
    skip = 0
    page_size = min(100, target)
    while len(all_notices) < target:
        current_limit = min(page_size, target - len(all_notices))
        payload = build_hilma_search_payload(
            limit=current_limit,
            skip=skip,
            published_after=published_after,
            published_before=published_before,
            include_expired=include_expired,
        )
        data = client.search_notices(payload)
        notices = extract_search_results(data)
        total_count = data.get("@odata.count", total_count)
        all_notices.extend(notices)
        if not notices or len(notices) < current_limit:
            break
        skip += current_limit
        if total_count is not None and len(all_notices) >= int(total_count):
            break
    metadata_payload = build_hilma_search_payload(
        limit=min(limit, 100),
        skip=0,
        published_after=published_after,
        published_before=published_before,
        include_expired=include_expired,
    )
    metadata = {
        "query": json.dumps(metadata_payload, ensure_ascii=False),
        "source": "Hilma AVP-Read",
        "published_after": published_after.isoformat(),
        "published_before": published_before.isoformat() if published_before else "",
        "include_expired": include_expired,
        "limit": limit,
        "total_count": total_count,
        "result_count": len(all_notices),
    }
    return all_notices, metadata


def hilma_filter(
    published_after: date,
    published_before: date | None,
    include_expired: bool,
    today: str,
    notice_type_filter: str,
) -> str:
    parts = [f"datePublished ge {published_after.isoformat()}T00:00:00Z"]
    if published_before:
        parts.append(f"datePublished lt {published_before.isoformat()}T00:00:00Z")
    if not include_expired:
        parts.append(f"deadline ge {today}T00:00:00Z")
    parts.append(f"({notice_type_filter})")
    return " and ".join(parts)


def extract_search_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("value"), list):
        return data["value"]
    if isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(data.get("notices"), list):
        return data["notices"]
    if isinstance(data.get("items"), list):
        return data["items"]
    raise HilmaApiError(f"Hilma search returned unexpected payload keys: {sorted(data.keys())}")


def write_cache(notices: list[dict[str, Any]], metadata: dict[str, Any], cache_dir: Path = CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "hilma_notices_sample.json"
    payload = {"source": "Hilma AVP-Read", "metadata": metadata, "notices": notices}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cache(path: Path = CACHE_DIR / "hilma_notices_sample.json") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"No cached Hilma data found at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("notices", []), payload.get("metadata", {})




def build_hilma_notice_url(raw: dict[str, Any], language: str = "fi") -> str:
    notice_id = first_available(raw, "noticeId", "notice_id", "hilmaNoticeId")
    procedure_id = first_available(raw, "procedureId", "eNoticeProcedureId")
    old_project_id = first_available(raw, "oldProcurementProjectId", "procurementProjectId", "projectId")
    app_url = "https://www.hankintailmoitukset.fi"
    lang = (language or "fi").lower()[:2]

    is_eforms = bool(raw.get("isEForms")) or str(first_available(raw, "id") or "").startswith("EF-")
    if is_eforms and procedure_id and notice_id:
        return f"{app_url}/{lang}/public/procedure/{procedure_id}/enotice/{notice_id}"
    if old_project_id and notice_id and str(old_project_id) != "0":
        return f"{app_url}/{lang}/public/procurement/{old_project_id}/notice/{notice_id}"

    explicit_url = first_available(raw, "url", "sourceUrl", "noticeUrl", "hilmaUrl")
    if explicit_url:
        return explicit_url
    if notice_id:
        return f"{app_url}/{lang}/search?text={notice_id}"
    notice_number = first_available(raw, "noticeNumber", "id") or ""
    return f"{app_url}/{lang}/search?text={notice_number}"

def normalize_notice(raw: dict[str, Any]) -> Notice:
    notice_id = first_available(raw, "noticeId", "notice_id", "hilmaNoticeId", "id")
    notice_number = first_available(raw, "noticeNumber", "id")
    title = first_available(raw, "titleFi", "titleEn", "titleSv", "titleOther", "title", "name", "noticeTitle", "procurementProjectName", "heading")
    buyer = first_available(
        raw,
        "organisationNameFi",
        "organisationNameEn",
        "organisationNameSv",
        "organisationNameOther",
        "buyerName",
        "contractingAuthorityName",
        "organisationName",
        "organizationName",
        "buyer",
    )
    country = first_available(raw, "country", "buyerCountry", "nutsCountry", "mainCountry") or "FIN"
    region_city = first_available(raw, "nutsCodes", "organisationNutsCode", "nutsCode", "location", "municipality", "region", "placeOfPerformance")
    deadline = first_available(raw, "deadline", "deadlineDate", "tenderDeadline", "timeLimitForReceipt")
    publication_date = first_available(raw, "datePublished", "published", "publicationDate", "created")
    notice_type = first_available(raw, "noticeType", "type", "formType")
    cpv_codes = collect_cpv_codes(raw)
    description = join_text(
        [
            first_available(raw, "descriptionFi", "descriptionEn", "descriptionSv", "descriptionOther"),
            *lot_texts(raw, ("descriptionFi", "descriptionEn", "descriptionSv", "descriptionOther")),
        ],
        max_chars=4000,
    )
    source_url = build_hilma_notice_url(raw)
    document_links = collect_urls(raw.get("procurementDocumentsUrl"), source_url)

    return Notice(
        publication_number=f"HILMA-{notice_number or notice_id or 'unknown'}",
        title=title or "Untitled Hilma notice",
        buyer=buyer or "Unknown buyer",
        country=country,
        region_city=region_city,
        deadline=deadline,
        source_url=source_url,
        cpv_codes=cpv_codes,
        document_links=document_links,
        raw_description=description,
        publication_date=publication_date,
        notice_type=notice_type,
        raw_notice=raw,
        source_name="Hilma AVP-Read",
    )


def first_available(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        text = first_text(value)
        if text:
            return text
    return ""


def flatten_keys(raw: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        if key in raw:
            value = raw[key]
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
    return values


def collect_cpv_codes(raw: dict[str, Any]) -> list[str]:
    values = flatten_keys(raw, ("cpv", "cpvCodes", "mainCpvCode", "classificationCodes"))
    for lot in raw.get("lots") or []:
        if isinstance(lot, dict):
            values.extend(flatten_keys(lot, ("cpv", "cpvCodes", "mainCpvCode", "classificationCodes")))
    codes: list[str] = []
    for value in values:
        text = str(value or "")
        chunks = re.findall(r"\d{8}", text)
        if chunks:
            codes.extend(chunks)
            continue
        for part in text.replace(";", ",").replace("//", ",").split(","):
            cleaned = "".join(ch for ch in part if ch.isdigit())
            if cleaned:
                codes.append(cleaned)
    return unique_strings(codes)


def lot_texts(raw: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    texts: list[str] = []
    for lot in raw.get("lots") or []:
        if isinstance(lot, dict):
            for key in keys:
                text = first_text(lot.get(key))
                if text:
                    texts.append(text)
    return texts
