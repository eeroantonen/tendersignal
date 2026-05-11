from __future__ import annotations

import json
from pathlib import Path

from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.database import connect, init_db
from tendersignal.hilma_urls import build_hilma_notice_url


def repair_hilma_source_urls(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    init_db(db_path)
    updates = {"notices": 0, "award_notices": 0, "winner_leads": 0}
    with connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for row in conn.execute(
            "SELECT publication_number, source_url, raw_notice, sales_briefing, document_links "
            "FROM notices WHERE source_name = 'Hilma AVP-Read'"
        ):
            raw = json.loads(row["raw_notice"] or "{}")
            new_url = build_hilma_notice_url(raw)
            if new_url == row["source_url"]:
                continue
            briefing = (row["sales_briefing"] or "").replace(row["source_url"], new_url)
            try:
                document_links = json.loads(row["document_links"] or "[]")
            except json.JSONDecodeError:
                document_links = []
            document_links = [new_url if item == row["source_url"] else item for item in document_links]
            conn.execute(
                "UPDATE notices SET source_url = ?, sales_briefing = ?, document_links = ? "
                "WHERE publication_number = ?",
                (new_url, briefing, json.dumps(document_links, ensure_ascii=False), row["publication_number"]),
            )
            updates["notices"] += 1

        if "award_notices" in tables:
            for row in conn.execute("SELECT award_id, source_url, raw_award FROM award_notices"):
                raw = json.loads(row["raw_award"] or "{}")
                new_url = build_hilma_notice_url(raw)
                if new_url != row["source_url"]:
                    conn.execute("UPDATE award_notices SET source_url = ? WHERE award_id = ?", (new_url, row["award_id"]))
                    updates["award_notices"] += 1

        if "winner_leads" in tables:
            for row in conn.execute("SELECT lead_id, source_url, raw_award FROM winner_leads"):
                raw = json.loads(row["raw_award"] or "{}")
                new_url = build_hilma_notice_url(raw)
                if new_url != row["source_url"]:
                    conn.execute("UPDATE winner_leads SET source_url = ? WHERE lead_id = ?", (new_url, row["lead_id"]))
                    updates["winner_leads"] += 1
    return updates
