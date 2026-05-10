from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.models import Notice, ScoredOpportunity


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notices (
                publication_number TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                buyer TEXT NOT NULL,
                country TEXT,
                region_city TEXT,
                deadline TEXT,
                source_url TEXT NOT NULL,
                cpv_codes TEXT NOT NULL,
                document_links TEXT NOT NULL DEFAULT '[]',
                raw_description TEXT,
                category TEXT,
                technical_trade_relevance_score REAL,
                pro_builder_relevance_score REAL,
                recommended_sales_action TEXT,
                account_segment TEXT NOT NULL DEFAULT '',
                sales_territory TEXT NOT NULL DEFAULT '',
                territory_owner TEXT NOT NULL DEFAULT '',
                mapping_evidence TEXT NOT NULL DEFAULT '',
                llm_enrichment_status TEXT NOT NULL DEFAULT 'disabled',
                evidence TEXT NOT NULL,
                uncertainties TEXT NOT NULL,
                sales_briefing TEXT NOT NULL,
                publication_date TEXT,
                notice_type TEXT,
                source_name TEXT NOT NULL,
                raw_notice TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """
        )
        ensure_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                source_name TEXT NOT NULL,
                query TEXT,
                status TEXT NOT NULL,
                notices_fetched INTEGER NOT NULL,
                error_message TEXT
            )
            """
        )


def upsert_opportunities(opportunities: list[ScoredOpportunity], db_path: Path = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    ingested_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO notices (
                publication_number, title, buyer, country, region_city, deadline, source_url,
                cpv_codes, document_links, raw_description, category, technical_trade_relevance_score,
                pro_builder_relevance_score, recommended_sales_action, account_segment, sales_territory,
                territory_owner, mapping_evidence, llm_enrichment_status, evidence, uncertainties,
                sales_briefing, publication_date, notice_type, source_name, raw_notice, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(publication_number) DO UPDATE SET
                title=excluded.title,
                buyer=excluded.buyer,
                country=excluded.country,
                region_city=excluded.region_city,
                deadline=excluded.deadline,
                source_url=excluded.source_url,
                cpv_codes=excluded.cpv_codes,
                document_links=excluded.document_links,
                raw_description=excluded.raw_description,
                category=excluded.category,
                technical_trade_relevance_score=excluded.technical_trade_relevance_score,
                pro_builder_relevance_score=excluded.pro_builder_relevance_score,
                recommended_sales_action=excluded.recommended_sales_action,
                account_segment=excluded.account_segment,
                sales_territory=excluded.sales_territory,
                territory_owner=excluded.territory_owner,
                mapping_evidence=excluded.mapping_evidence,
                llm_enrichment_status=excluded.llm_enrichment_status,
                evidence=excluded.evidence,
                uncertainties=excluded.uncertainties,
                sales_briefing=excluded.sales_briefing,
                publication_date=excluded.publication_date,
                notice_type=excluded.notice_type,
                source_name=excluded.source_name,
                raw_notice=excluded.raw_notice,
                ingested_at=excluded.ingested_at
            """,
            [opportunity_to_row(item, ingested_at) for item in opportunities],
        )


def record_ingestion_run(
    status: str,
    notices_fetched: int,
    query: str = "",
    error_message: str = "",
    source_name: str = "TED Search API",
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingestion_runs (run_at, source_name, query, status, notices_fetched, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (datetime.now(timezone.utc).isoformat(), source_name, query, status, notices_fetched, error_message),
        )


def opportunity_to_row(opportunity: ScoredOpportunity, ingested_at: str) -> tuple:
    notice = opportunity.notice
    return (
        notice.publication_number,
        notice.title,
        notice.buyer,
        notice.country,
        notice.region_city,
        notice.deadline,
        notice.source_url,
        json.dumps(notice.cpv_codes, ensure_ascii=False),
        json.dumps(notice.document_links, ensure_ascii=False),
        notice.raw_description,
        opportunity.category,
        opportunity.technical_trade_relevance_score,
        opportunity.pro_builder_relevance_score,
        opportunity.recommended_sales_action,
        opportunity.account_segment,
        opportunity.sales_territory,
        opportunity.territory_owner,
        opportunity.mapping_evidence,
        opportunity.llm_enrichment_status,
        json.dumps(opportunity.evidence, ensure_ascii=False),
        json.dumps(opportunity.uncertainties, ensure_ascii=False),
        opportunity.sales_briefing,
        notice.publication_date,
        notice.notice_type,
        notice.source_name,
        json.dumps(notice.raw_notice, ensure_ascii=False),
        ingested_at,
    )


def ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(notices)")}
    columns = {
        "document_links": "TEXT NOT NULL DEFAULT '[]'",
        "account_segment": "TEXT NOT NULL DEFAULT ''",
        "sales_territory": "TEXT NOT NULL DEFAULT ''",
        "territory_owner": "TEXT NOT NULL DEFAULT ''",
        "mapping_evidence": "TEXT NOT NULL DEFAULT ''",
        "llm_enrichment_status": "TEXT NOT NULL DEFAULT 'disabled'",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE notices ADD COLUMN {name} {definition}")


def load_opportunities(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    init_db(db_path)
    with connect(db_path) as conn:
        return list(
            conn.execute(
                """
                SELECT * FROM notices
                ORDER BY MAX(technical_trade_relevance_score, pro_builder_relevance_score) DESC,
                         deadline ASC
                """
            )
        )


def load_ingestion_runs(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    init_db(db_path)
    with connect(db_path) as conn:
        return list(conn.execute("SELECT * FROM ingestion_runs ORDER BY run_at DESC LIMIT 25"))
