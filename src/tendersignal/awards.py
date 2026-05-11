from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from tendersignal.config import CACHE_DIR, DEFAULT_DB_PATH
from tendersignal.database import connect, init_db, record_ingestion_run
from tendersignal.sources.hilma import HilmaClient, build_hilma_notice_url, extract_search_results
from tendersignal.text import first_text, unique_strings

K_GROUP_TERMS = ("Onninen Oy", "Onninen", "Kesko Oyj", "K-Rauta", "K Rauta")
COMPETITOR_TERMS = ("Ahlsell", "Dahl Suomi", "Sonepar", "Rexel", "LVI-Dahl", "Solar")
AWARD_NOTICE_TYPES = ("29", "30", "31", "32", "33", "34", "35", "36", "37", "E4")


def build_award_payload(search_term: str, days_back: int = 1460, limit: int = 100) -> dict[str, Any]:
    published_after = (date.today() - timedelta(days=days_back)).isoformat()
    notice_type_filter = " or ".join(f"type eq '{notice_type}'" for notice_type in AWARD_NOTICE_TYPES)
    return {
        "search": search_term,
        "top": min(limit, 100),
        "count": True,
        "filter": f"datePublished ge {published_after}T00:00:00Z and ({notice_type_filter})",
        "orderby": "datePublished desc",
    }


def fetch_hilma_awards(
    days_back: int = 1460,
    limit_per_term: int = 100,
    search_terms: tuple[str, ...] = K_GROUP_TERMS + COMPETITOR_TERMS,
    client: HilmaClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = client or HilmaClient()
    awards_by_key: dict[str, dict[str, Any]] = {}
    queries: list[dict[str, Any]] = []
    for term in search_terms:
        payload = build_award_payload(term, days_back=days_back, limit=limit_per_term)
        data = client.search_notices(payload)
        queries.append({"term": term, "payload": payload, "count": data.get("@odata.count")})
        for raw in extract_search_results(data):
            key = str(raw.get("noticeNumber") or raw.get("id") or raw.get("noticeId"))
            existing = awards_by_key.setdefault(key, raw)
            existing_terms = set(existing.get("_matched_search_terms", []))
            existing_terms.add(term)
            existing["_matched_search_terms"] = sorted(existing_terms)
    metadata = {
        "source": "Hilma AVP-Read award search",
        "query": json.dumps(queries, ensure_ascii=False),
        "days_back": days_back,
        "limit_per_term": limit_per_term,
        "result_count": len(awards_by_key),
    }
    return list(awards_by_key.values()), metadata


def write_award_cache(awards: list[dict[str, Any]], metadata: dict[str, Any], cache_dir: Path = CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "hilma_awards_sample.json"
    path.write_text(json.dumps({"source": "Hilma AVP-Read award search", "metadata": metadata, "awards": awards}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_award_cache(path: Path = CACHE_DIR / "hilma_awards_sample.json") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"No cached Hilma award data found at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("awards", []), payload.get("metadata", {})


def normalize_award(raw: dict[str, Any]) -> list[dict[str, Any]]:
    winners = first_text(raw.get("winnerOrganisations"))
    matched = match_suppliers(winners)
    if not matched:
        return []
    rows = []
    for group, supplier in matched:
        notice_number = first_text(raw.get("noticeNumber")) or first_text(raw.get("id"))
        award_id = f"HILMA-AWARD-{notice_number}-{slug(supplier)}"
        rows.append(
            {
                "award_id": award_id,
                "source_name": "Hilma AVP-Read",
                "notice_number": notice_number,
                "notice_id": first_text(raw.get("noticeId")),
                "title": first_text(raw.get("titleFi")) or first_text(raw.get("titleEn")) or first_text(raw.get("titleSv")) or "Untitled award notice",
                "buyer": first_text(raw.get("organisationNameFi")) or first_text(raw.get("organisationNameEn")) or "Unknown buyer",
                "publication_date": first_text(raw.get("datePublished")),
                "notice_type": first_text(raw.get("type")),
                "cpv_codes": json.dumps(collect_award_cpv(raw), ensure_ascii=False),
                "region_city": first_text(raw.get("nutsCodes")) or first_text(raw.get("organisationNutsCode")),
                "winner_organisations": winners,
                "matched_supplier": supplier,
                "match_group": group,
                "amount": raw.get("noticeResultTotalAmount"),
                "currency": first_text(raw.get("noticeResultTotalAmountCurrency")),
                "contract_end_or_expiration": first_text(raw.get("expirationDate")),
                "source_url": build_hilma_notice_url(raw),
                "raw_award": json.dumps(raw, ensure_ascii=False),
            }
        )
    return rows


def match_suppliers(winners: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for term in K_GROUP_TERMS:
        if contains(winners, term):
            matches.append(("K Group", canonical_supplier(term)))
    for term in COMPETITOR_TERMS:
        if contains(winners, term):
            matches.append(("Competitor", canonical_supplier(term)))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in matches:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def canonical_supplier(term: str) -> str:
    lookup = {
        "Onninen": "Onninen Oy",
        "Onninen Oy": "Onninen Oy",
        "Kesko Oyj": "Kesko Oyj / Kespro",
        "K-Rauta": "K-Rauta",
        "K Rauta": "K-Rauta",
        "Dahl Suomi": "Dahl Suomi Oy",
        "LVI-Dahl": "Dahl Suomi Oy",
    }
    return lookup.get(term, term)


def contains(text: str, term: str) -> bool:
    return bool(text and re.search(re.escape(term), text, flags=re.IGNORECASE))


def collect_award_cpv(raw: dict[str, Any]) -> list[str]:
    values = [raw.get("cpvCodes")]
    for lot in raw.get("lots") or []:
        if isinstance(lot, dict):
            values.append(lot.get("cpvCodes"))
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


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower() or "unknown"


def init_awards_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS award_notices (
                award_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                notice_number TEXT,
                notice_id TEXT,
                title TEXT NOT NULL,
                buyer TEXT NOT NULL,
                publication_date TEXT,
                notice_type TEXT,
                cpv_codes TEXT NOT NULL,
                region_city TEXT,
                winner_organisations TEXT,
                matched_supplier TEXT,
                match_group TEXT,
                amount REAL,
                currency TEXT,
                contract_end_or_expiration TEXT,
                source_url TEXT,
                raw_award TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """
        )


def upsert_awards(awards: list[dict[str, Any]], db_path: Path = DEFAULT_DB_PATH) -> None:
    init_awards_db(db_path)
    ingested_at = pd.Timestamp.utcnow().isoformat()
    rows: list[dict[str, Any]] = []
    for raw in awards:
        rows.extend(normalize_award(raw))
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO award_notices (
                award_id, source_name, notice_number, notice_id, title, buyer, publication_date,
                notice_type, cpv_codes, region_city, winner_organisations, matched_supplier,
                match_group, amount, currency, contract_end_or_expiration, source_url, raw_award, ingested_at
            )
            VALUES (
                :award_id, :source_name, :notice_number, :notice_id, :title, :buyer, :publication_date,
                :notice_type, :cpv_codes, :region_city, :winner_organisations, :matched_supplier,
                :match_group, :amount, :currency, :contract_end_or_expiration, :source_url, :raw_award, :ingested_at
            )
            ON CONFLICT(award_id) DO UPDATE SET
                source_name=excluded.source_name,
                notice_number=excluded.notice_number,
                notice_id=excluded.notice_id,
                title=excluded.title,
                buyer=excluded.buyer,
                publication_date=excluded.publication_date,
                notice_type=excluded.notice_type,
                cpv_codes=excluded.cpv_codes,
                region_city=excluded.region_city,
                winner_organisations=excluded.winner_organisations,
                matched_supplier=excluded.matched_supplier,
                match_group=excluded.match_group,
                amount=excluded.amount,
                currency=excluded.currency,
                contract_end_or_expiration=excluded.contract_end_or_expiration,
                source_url=excluded.source_url,
                raw_award=excluded.raw_award,
                ingested_at=excluded.ingested_at
            """,
            [dict(row, ingested_at=ingested_at) for row in rows],
        )


def run_hilma_award_ingestion(db_path: Path = DEFAULT_DB_PATH, days_back: int = 1460, use_cache: bool = False) -> int:
    query = ""
    try:
        if use_cache:
            awards, metadata = load_award_cache()
        else:
            awards, metadata = fetch_hilma_awards(days_back=days_back)
            write_award_cache(awards, metadata)
        query = metadata.get("query", "")
        upsert_awards(awards, db_path)
        record_ingestion_run("success", len(awards), query=query, source_name="Hilma AVP-Read awards", db_path=db_path)
        return len(awards)
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="Hilma AVP-Read awards", db_path=db_path)
        raise


def load_awards_dataframe(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    init_awards_db(db_path)
    with connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM award_notices ORDER BY publication_date DESC")]
    if not rows:
        return pd.DataFrame(
            columns=[
                "award_id",
                "source_name",
                "notice_number",
                "title",
                "buyer",
                "publication_date",
                "matched_supplier",
                "match_group",
                "amount",
                "currency",
                "contract_end_or_expiration",
                "source_url",
            ]
        )
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df
