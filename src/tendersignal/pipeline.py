from __future__ import annotations

from pathlib import Path
from datetime import date

from tendersignal.account_mapping import apply_territory_mapping, load_rules
from tendersignal.briefing import build_sales_briefing
from tendersignal.classifier import classify_notice
from tendersignal.database import record_ingestion_run, upsert_opportunities
from tendersignal.llm.null import NullEnricher
from tendersignal.llm.openai_enricher import build_optional_enricher
from tendersignal.sources.ted import fetch_ted_notices, fetch_ted_notices_for_period, load_cache, normalize_notice, write_cache
from tendersignal.sources import hilma


def run_ingestion(
    db_path: Path,
    days_back: int = 21,
    limit: int = 100,
    use_cache: bool = False,
    write_sample_cache: bool = True,
) -> int:
    query = ""
    try:
        if use_cache:
            raw_notices, metadata = load_cache()
        else:
            raw_notices, metadata = fetch_ted_notices(days_back=days_back, limit=limit)
            if write_sample_cache:
                write_cache(raw_notices, metadata)
        query = metadata.get("query", "")
        territory_rules = load_rules()
        enricher = build_optional_enricher() or NullEnricher()
        opportunities = []
        for raw in raw_notices:
            notice = normalize_notice(raw)
            opportunity = classify_notice(notice)
            opportunity = apply_territory_mapping(opportunity, territory_rules)
            opportunity.sales_briefing = build_sales_briefing(opportunity)
            opportunities.append(enricher.enrich(opportunity))
        upsert_opportunities(opportunities, db_path)
        record_ingestion_run("success", len(opportunities), query=query, source_name="TED Search API", db_path=db_path)
        return len(opportunities)
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="TED Search API", db_path=db_path)
        raise


def run_ted_ingestion_for_period(
    db_path: Path,
    published_after: date,
    published_before: date,
    limit: int = 5000,
    write_sample_cache: bool = True,
) -> int:
    query = ""
    try:
        raw_notices, metadata = fetch_ted_notices_for_period(
            published_after=published_after,
            published_before=published_before,
            limit=limit,
        )
        if write_sample_cache:
            write_cache(raw_notices, metadata)
        query = metadata.get("query", "")
        return process_raw_notices(raw_notices, metadata, db_path, source_name="TED Search API")
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="TED Search API", db_path=db_path)
        raise


def run_hilma_ingestion(
    db_path: Path,
    days_back: int = 21,
    limit: int = 100,
    use_cache: bool = False,
    write_sample_cache: bool = True,
) -> int:
    query = ""
    try:
        if use_cache:
            raw_notices, metadata = hilma.load_cache()
        else:
            raw_notices, metadata = hilma.fetch_hilma_notices(days_back=days_back, limit=limit)
            if write_sample_cache:
                hilma.write_cache(raw_notices, metadata)
        query = metadata.get("query", "")
        territory_rules = load_rules()
        enricher = build_optional_enricher() or NullEnricher()
        opportunities = []
        for raw in raw_notices:
            notice = hilma.normalize_notice(raw)
            opportunity = classify_notice(notice)
            opportunity = apply_territory_mapping(opportunity, territory_rules)
            opportunity.sales_briefing = build_sales_briefing(opportunity)
            opportunities.append(enricher.enrich(opportunity))
        upsert_opportunities(opportunities, db_path)
        record_ingestion_run("success", len(opportunities), query=query, source_name="Hilma AVP-Read", db_path=db_path)
        return len(opportunities)
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="Hilma AVP-Read", db_path=db_path)
        raise


def run_hilma_ingestion_for_period(
    db_path: Path,
    published_after: date,
    published_before: date | None,
    limit: int = 5000,
    include_expired: bool = True,
    write_sample_cache: bool = True,
) -> int:
    query = ""
    try:
        raw_notices, metadata = hilma.fetch_hilma_notices_for_period(
            published_after=published_after,
            published_before=published_before,
            limit=limit,
            include_expired=include_expired,
        )
        if write_sample_cache:
            hilma.write_cache(raw_notices, metadata)
        query = metadata.get("query", "")
        count = process_hilma_raw_notices(raw_notices, db_path)
        record_ingestion_run("success", count, query=query, source_name="Hilma AVP-Read", db_path=db_path)
        return count
    except Exception as exc:
        record_ingestion_run("failed", 0, query=query, error_message=str(exc), source_name="Hilma AVP-Read", db_path=db_path)
        raise


def process_raw_notices(raw_notices: list[dict], metadata: dict, db_path: Path, source_name: str) -> int:
    territory_rules = load_rules()
    enricher = build_optional_enricher() or NullEnricher()
    opportunities = []
    for raw in raw_notices:
        notice = normalize_notice(raw)
        opportunity = classify_notice(notice)
        opportunity = apply_territory_mapping(opportunity, territory_rules)
        opportunity.sales_briefing = build_sales_briefing(opportunity)
        opportunities.append(enricher.enrich(opportunity))
    upsert_opportunities(opportunities, db_path)
    record_ingestion_run("success", len(opportunities), query=metadata.get("query", ""), source_name=source_name, db_path=db_path)
    return len(opportunities)


def process_hilma_raw_notices(raw_notices: list[dict], db_path: Path) -> int:
    territory_rules = load_rules()
    enricher = build_optional_enricher() or NullEnricher()
    opportunities = []
    for raw in raw_notices:
        notice = hilma.normalize_notice(raw)
        opportunity = classify_notice(notice)
        opportunity = apply_territory_mapping(opportunity, territory_rules)
        opportunity.sales_briefing = build_sales_briefing(opportunity)
        opportunities.append(enricher.enrich(opportunity))
    upsert_opportunities(opportunities, db_path)
    return len(opportunities)
