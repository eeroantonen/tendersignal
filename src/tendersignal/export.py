from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from tendersignal.config import DEFAULT_DB_PATH, EXPORT_DIR
from tendersignal.business import add_business_columns
from tendersignal.database import load_opportunities

EXPORT_COLUMNS = [
    "public_data_source",
    "k_business_lane",
    "k_priority_score",
    "k_priority_band",
    "strategic_demand_signal",
    "recommended_k_action",
    "title",
    "buyer",
    "country",
    "region_city",
    "deadline",
    "source_url",
    "cpv_codes",
    "document_links",
    "raw_description",
    "category",
    "technical_trade_relevance_score",
    "pro_builder_relevance_score",
    "account_segment",
    "sales_territory",
    "territory_owner",
    "mapping_evidence",
    "llm_enrichment_status",
    "recommended_sales_action",
    "evidence",
    "uncertainties",
]


def opportunities_dataframe(db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    rows = [dict(row) for row in load_opportunities(db_path)]
    if not rows:
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    for row in rows:
        row["cpv_codes"] = ", ".join(json.loads(row.get("cpv_codes") or "[]"))
        row["document_links"] = " | ".join(json.loads(row.get("document_links") or "[]"))
        row["evidence"] = " | ".join(json.loads(row.get("evidence") or "[]"))
        row["uncertainties"] = " | ".join(json.loads(row.get("uncertainties") or "[]"))
    return add_business_columns(pd.DataFrame(rows))


def export_csv(db_path: Path = DEFAULT_DB_PATH, export_dir: Path = EXPORT_DIR) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    df = opportunities_dataframe(db_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = export_dir / f"tendersignal_opportunities_{timestamp}.csv"
    df[EXPORT_COLUMNS].to_csv(path, index=False)
    return path
