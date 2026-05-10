from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Notice:
    publication_number: str
    title: str
    buyer: str
    country: str
    region_city: str
    deadline: str
    source_url: str
    cpv_codes: list[str]
    document_links: list[str]
    raw_description: str
    publication_date: str
    notice_type: str
    raw_notice: dict[str, Any]
    source_name: str = "TED Search API"


@dataclass
class ScoredOpportunity:
    notice: Notice
    category: str
    technical_trade_relevance_score: float
    pro_builder_relevance_score: float
    recommended_sales_action: str
    evidence: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    account_segment: str = ""
    sales_territory: str = ""
    territory_owner: str = ""
    mapping_evidence: str = ""
    llm_enrichment_status: str = "disabled"
    sales_briefing: str = ""
