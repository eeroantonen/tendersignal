from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from tendersignal.awards import AWARD_NOTICE_TYPES, collect_award_cpv, slug
from tendersignal.config import CACHE_DIR, DEFAULT_DB_PATH
from tendersignal.database import connect, init_db, record_ingestion_run
from tendersignal.sources.hilma import HilmaClient, build_hilma_notice_url, extract_search_results
from tendersignal.text import first_text

WINNER_LEAD_SEARCH_TERMS = (
    "rakennusurakka",
    "sähköurakka",
    "LVI",
    "ilmanvaihto",
    "putkiurakka",
    "maanrakennus",
    "peruskorjaus",
    "julkisivu",
    "kaukolämpö",
    "kunnossapito",
)

TECHNICAL_PREFIXES = ("31", "312", "313", "315", "316", "397", "421", "425", "4416", "45231", "45232", "4531", "4533", "507", "642")
PRO_BUILDER_PREFIXES = ("43", "44", "441", "442", "443", "445", "451", "452", "453", "454", "455")
TECHNICAL_TERMS = ("sähkö", "lvi", "ilmanvaihto", "putki", "kaukolämpö", "ventilation", "electrical", "hvac", "plumbing")
PRO_BUILDER_TERMS = ("rakennus", "maanrakennus", "peruskorjaus", "julkisivu", "korjaus", "construction", "renovation", "building")
VALUE_KEYS = (
    ("noticeResultTotalAmount", "noticeResultTotalAmountCurrency"),
    ("overallMaximumFrameworkContractsAmount", "overallMaximumFrameworkContractsCurrency"),
    ("overallApproximateFrameworkContractsAmount", "overallApproximateFrameworkContractsCurrency"),
    ("estimatedValue", "currency"),
)


def build_winner_lead_payload(search_term: str, days_back: int = 1460, limit: int = 100) -> dict[str, Any]:
    published_after = (date.today() - timedelta(days=days_back)).isoformat()
    notice_type_filter = " or ".join(f"type eq '{notice_type}'" for notice_type in AWARD_NOTICE_TYPES)
    return {
        "search": search_term,
        "top": min(limit, 100),
        "count": True,
        "filter": f"datePublished ge {published_after}T00:00:00Z and ({notice_type_filter})",
        "orderby": "datePublished desc",
    }


def fetch_hilma_winner_leads(
    days_back: int = 1460,
    limit_per_term: int = 100,
    search_terms: tuple[str, ...] = WINNER_LEAD_SEARCH_TERMS,
    client: HilmaClient | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = client or HilmaClient()
    awards_by_key: dict[str, dict[str, Any]] = {}
    queries: list[dict[str, Any]] = []
    for term in search_terms:
        payload = build_winner_lead_payload(term, days_back=days_back, limit=limit_per_term)
        data = client.search_notices(payload)
        queries.append({"term": term, "payload": payload, "count": data.get("@odata.count")})
        for raw in extract_search_results(data):
            key = str(raw.get("noticeNumber") or raw.get("id") or raw.get("noticeId"))
            existing = awards_by_key.setdefault(key, raw)
            existing_terms = set(existing.get("_matched_search_terms", []))
            existing_terms.add(term)
            existing["_matched_search_terms"] = sorted(existing_terms)
    metadata = {
        "source": "Hilma AVP-Read winner lead search",
        "query": json.dumps(queries, ensure_ascii=False),
        "days_back": days_back,
        "limit_per_term": limit_per_term,
        "result_count": len(awards_by_key),
    }
    return list(awards_by_key.values()), metadata


def write_winner_lead_cache(awards: list[dict[str, Any]], metadata: dict[str, Any], cache_dir: Path = CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "hilma_winner_leads_sample.json"
    path.write_text(json.dumps({"source": "Hilma AVP-Read winner lead search", "metadata": metadata, "awards": awards}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_winner_lead_cache(path: Path = CACHE_DIR / "hilma_winner_leads_sample.json") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"No cached Hilma winner lead data found at {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("awards", []), payload.get("metadata", {})


def split_winner_organisations(value: str) -> list[str]:
    parts = re.split(r"//|;|\n|\r", value or "")
    winners: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" ,")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            winners.append(cleaned)
            seen.add(key)
    return winners


def normalize_winner_leads(raw: dict[str, Any]) -> list[dict[str, Any]]:
    winners = split_winner_organisations(first_text(raw.get("winnerOrganisations")))
    if not winners:
        return []
    cpv_codes = collect_award_cpv(raw)
    amount, currency = award_value(raw)
    category = lead_category(cpv_codes, raw)
    lane = lead_lane(cpv_codes, raw)
    score, evidence, uncertainties = score_winner_lead(raw, cpv_codes, amount, lane, winners)
    rows = []
    for winner in winners:
        notice_number = first_text(raw.get("noticeNumber")) or first_text(raw.get("id"))
        rows.append(
            {
                "lead_id": f"HILMA-WINNER-{notice_number}-{slug(winner)}",
                "source_name": "Hilma AVP-Read",
                "notice_number": notice_number,
                "notice_id": first_text(raw.get("noticeId")),
                "title": first_text(raw.get("titleFi")) or first_text(raw.get("titleEn")) or first_text(raw.get("titleSv")) or "Untitled award notice",
                "buyer": first_text(raw.get("organisationNameFi")) or first_text(raw.get("organisationNameEn")) or "Unknown buyer",
                "winner_organisation": winner,
                "publication_date": first_text(raw.get("datePublished")),
                "notice_type": first_text(raw.get("type")),
                "cpv_codes": json.dumps(cpv_codes, ensure_ascii=False),
                "category": category,
                "k_business_lane": lane,
                "region_city": first_text(raw.get("nutsCodes")) or first_text(raw.get("organisationNutsCode")),
                "amount": amount,
                "currency": currency,
                "contract_end_or_expiration": first_text(raw.get("expirationDate")),
                "lead_score": score,
                "recommended_action": recommended_winner_action(lane, winner, category),
                "evidence": json.dumps(evidence, ensure_ascii=False),
                "uncertainties": json.dumps(uncertainties, ensure_ascii=False),
                "source_url": build_hilma_notice_url(raw),
                "raw_award": json.dumps(raw, ensure_ascii=False),
            }
        )
    return rows


def award_value(raw: dict[str, Any]) -> tuple[float | None, str]:
    for amount_key, currency_key in VALUE_KEYS:
        value = raw.get(amount_key)
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return amount, first_text(raw.get(currency_key)) or "EUR"
    return None, ""


def lead_lane(cpv_codes: list[str], raw: dict[str, Any]) -> str:
    text = searchable_award_text(raw)
    technical_cpv = any(matches_prefix(code, TECHNICAL_PREFIXES) for code in cpv_codes)
    technical_text = any(term in text for term in TECHNICAL_TERMS)
    pro_specific_prefixes = tuple(prefix for prefix in PRO_BUILDER_PREFIXES if prefix != "453")
    pro_cpv = any(matches_prefix(code, pro_specific_prefixes) for code in cpv_codes)
    pro_text = any(term in text for term in PRO_BUILDER_TERMS)
    shared_installation_pro = any(matches_prefix(code, ("453",)) for code in cpv_codes) and pro_text
    technical = technical_cpv or technical_text
    pro = pro_cpv or shared_installation_pro or pro_text
    if technical and pro:
        return "Joint B2B opportunity"
    if technical:
        return "Onninen technical trade"
    if pro:
        return "K-Rauta Pro builder retail"
    return "Monitor / weak fit"


def lead_category(cpv_codes: list[str], raw: dict[str, Any]) -> str:
    lane = lead_lane(cpv_codes, raw)
    text = searchable_award_text(raw)
    if "sähkö" in text or "electrical" in text:
        return "Electrical contractor / technical installation"
    if "lvi" in text or "ilmanvaihto" in text or "putki" in text or "hvac" in text:
        return "HVAC, plumbing or ventilation contractor"
    if "maanrakennus" in text or "infra" in text or any(matches_prefix(code, ("451", "4523")) for code in cpv_codes):
        return "Civil works / infrastructure contractor"
    if "peruskorjaus" in text or "julkisivu" in text or "korjaus" in text:
        return "Renovation contractor"
    if lane == "K-Rauta Pro builder retail":
        return "Building contractor / materials lead"
    if lane == "Onninen technical trade":
        return "Technical trade contractor lead"
    return "General public award lead"


def score_winner_lead(raw: dict[str, Any], cpv_codes: list[str], amount: float | None, lane: str, winners: list[str]) -> tuple[float, list[str], list[str]]:
    evidence: list[str] = []
    uncertainties: list[str] = []
    score = 0.0
    if lane != "Monitor / weak fit":
        score += 35
        evidence.append(f"Relevant lane from CPV/text: {lane}.")
    else:
        uncertainties.append("No strong Onninen or K-Rauta Pro CPV/text match.")
    if amount:
        if amount >= 1_000_000:
            score += 25
        elif amount >= 250_000:
            score += 18
        else:
            score += 10
        evidence.append(f"Public award/framework value returned: {amount:,.0f}.")
    else:
        uncertainties.append("No public award value field returned.")
    recency = recency_points(first_text(raw.get("datePublished")))
    score += recency
    evidence.append(f"Award recency component {recency}/15 from publication date.")
    if first_text(raw.get("nutsCodes")) or first_text(raw.get("organisationAddress")):
        score += 10
        evidence.append("Location evidence returned by Hilma fields.")
    else:
        uncertainties.append("No city/location evidence beyond buyer name.")
    if winners:
        score += 10
        evidence.append("Winner organisation field is present.")
    if first_text(raw.get("expirationDate")):
        score += 5
        evidence.append("Expiration/contract end field is available for renewal watch.")
    return min(100.0, score), evidence, uncertainties


def recency_points(value: str) -> int:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return 0
    days = (pd.Timestamp.utcnow() - parsed).days
    if days <= 365:
        return 15
    if days <= 730:
        return 10
    if days <= 1460:
        return 5
    return 0


def recommended_winner_action(lane: str, winner: str, category: str) -> str:
    if lane == "Onninen technical trade":
        return f"Route winner {winner} to Onninen sales; validate awarded lots and prepare offer around {category}."
    if lane == "K-Rauta Pro builder retail":
        return f"Route winner {winner} to K-Rauta Pro; check site supply, tools, logistics and materials needs for {category}."
    if lane == "Joint B2B opportunity":
        return f"Coordinate Onninen and K-Rauta Pro approach to winner {winner}; award suggests both technical and builder supply potential."
    return f"Monitor winner {winner}; use only if local sales recognises the account or category fit strengthens."


def searchable_award_text(raw: dict[str, Any]) -> str:
    return " ".join(
        first_text(raw.get(field)).lower()
        for field in ("titleFi", "titleEn", "descriptionFi", "descriptionEn", "cpvCodes", "_matched_search_terms")
    )


def matches_prefix(code: str, prefixes: tuple[str, ...]) -> bool:
    digits = re.sub(r"\D", "", str(code or ""))
    return any(digits.startswith(prefix) for prefix in prefixes)


def init_winner_leads_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS winner_leads (
                lead_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                notice_number TEXT,
                notice_id TEXT,
                title TEXT NOT NULL,
                buyer TEXT NOT NULL,
                winner_organisation TEXT NOT NULL,
                publication_date TEXT,
                notice_type TEXT,
                cpv_codes TEXT NOT NULL,
                category TEXT,
                k_business_lane TEXT,
                region_city TEXT,
                amount REAL,
                currency TEXT,
                contract_end_or_expiration TEXT,
                lead_score REAL,
                recommended_action TEXT,
                evidence TEXT NOT NULL,
                uncertainties TEXT NOT NULL,
                source_url TEXT,
                raw_award TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """
        )


def upsert_winner_leads(awards: list[dict[str, Any]], db_path: Path = DEFAULT_DB_PATH) -> int:
    init_winner_leads_db(db_path)
    ingested_at = pd.Timestamp.utcnow().isoformat()
    rows: list[dict[str, Any]] = []
    for raw in awards:
        rows.extend(normalize_winner_leads(raw))
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO winner_leads (
                lead_id, source_name, notice_number, notice_id, title, buyer, winner_organisation,
                publication_date, notice_type, cpv_codes, category, k_business_lane, region_city,
                amount, currency, contract_end_or_expiration, lead_score, recommended_action,
                evidence, uncertainties, source_url, raw_award, ingested_at
            )
            VALUES (
                :lead_id, :source_name, :notice_number, :notice_id, :title, :buyer, :winner_organisation,
                :publication_date, :notice_type, :cpv_codes, :category, :k_business_lane, :region_city,
                :amount, :currency, :contract_end_or_expiration, :lead_score, :recommended_action,
                :evidence, :uncertainties, :source_url, :raw_award, :ingested_at
            )
            ON CONFLICT(lead_id) DO UPDATE SET
                source_name=excluded.source_name,
                notice_number=excluded.notice_number,
                notice_id=excluded.notice_id,
                title=excluded.title,
                buyer=excluded.buyer,
                winner_organisation=excluded.winner_organisation,
                publication_date=excluded.publication_date,
                notice_type=excluded.notice_type,
                cpv_codes=excluded.cpv_codes,
                category=excluded.category,
                k_business_lane=excluded.k_business_lane,
                region_city=excluded.region_city,
                amount=excluded.amount,
                currency=excluded.currency,
                contract_end_or_expiration=excluded.contract_end_or_expiration,
                lead_score=excluded.lead_score,
                recommended_action=excluded.recommended_action,
                evidence=excluded.evidence,
                uncertainties=excluded.uncertainties,
                source_url=excluded.source_url,
                raw_award=excluded.raw_award,
                ingested_at=excluded.ingested_at
            """,
            [dict(row, ingested_at=ingested_at) for row in rows],
        )
    return len(rows)


def run_hilma_winner_lead_ingestion(db_path: Path = DEFAULT_DB_PATH, days_back: int = 1460, use_cache: bool = False) -> int:
    query = ""
    try:
        if use_cache:
            awards, metadata = load_winner_lead_cache()
        else:
            awards, metadata = fetch_hilma_winner_leads(days_back=days_back)
            write_winner_lead_cache(awards, metadata)
        query = metadata.get("query", "")
        count = upsert_winner_leads(awards, db_path)
        record_ingestion_run("success", count, query=query, source_name="Hilma AVP-Read winner leads", db_path=db_path)
        return count
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="Hilma AVP-Read winner leads", db_path=db_path)
        raise


def load_winner_leads_dataframe(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    init_winner_leads_db(db_path)
    with connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM winner_leads ORDER BY lead_score DESC, publication_date DESC")]
    if not rows:
        return pd.DataFrame(
            columns=[
                "lead_id",
                "title",
                "buyer",
                "winner_organisation",
                "publication_date",
                "cpv_codes",
                "category",
                "k_business_lane",
                "amount",
                "currency",
                "contract_end_or_expiration",
                "lead_score",
                "recommended_action",
                "source_url",
                "raw_award",
            ]
        )
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["lead_score"] = pd.to_numeric(df["lead_score"], errors="coerce")
    return df
