from __future__ import annotations

import json
import os

from tendersignal.config import TENDERSIGNAL_ENABLE_LLM, TENDERSIGNAL_LLM_MODEL, TENDERSIGNAL_LLM_PROVIDER
from tendersignal.models import ScoredOpportunity


class OpenAIEnricher:
    """Optional source-constrained LLM enrichment.

    This is disabled unless `TENDERSIGNAL_ENABLE_LLM=1`,
    `TENDERSIGNAL_LLM_PROVIDER=openai`, and `OPENAI_API_KEY` are set.
    """

    def __init__(self, model: str = TENDERSIGNAL_LLM_MODEL) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the optional LLM dependency with `pip install -e '.[llm]'`.") from exc
        self.client = OpenAI()
        self.model = model

    def enrich(self, opportunity: ScoredOpportunity) -> ScoredOpportunity:
        payload = source_payload(opportunity)
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "You enrich public procurement opportunity briefings. Use only the supplied JSON fields. "
                "Do not add buyer facts, contract values, requirements, customers, or deadlines unless present. "
                "Return compact JSON with keys: briefing_addendum, extra_uncertainties. "
                "If evidence is insufficient, say so in extra_uncertainties."
            ),
            input=json.dumps(payload, ensure_ascii=False),
            text={"format": {"type": "json_object"}},
            temperature=0,
        )
        raw_text = getattr(response, "output_text", "")
        try:
            enriched = json.loads(raw_text)
        except json.JSONDecodeError:
            opportunity.llm_enrichment_status = "failed: non-json response"
            opportunity.uncertainties.append("LLM enrichment returned non-JSON output and was not applied.")
            return opportunity

        addendum = str(enriched.get("briefing_addendum", "")).strip()
        if addendum:
            opportunity.sales_briefing += f"\n\nOptional LLM addendum, source-constrained: {addendum}"
        for item in enriched.get("extra_uncertainties", []) or []:
            text = str(item).strip()
            if text and text not in opportunity.uncertainties:
                opportunity.uncertainties.append(text)
        opportunity.llm_enrichment_status = "applied"
        return opportunity


def build_optional_enricher() -> OpenAIEnricher | None:
    if not TENDERSIGNAL_ENABLE_LLM:
        return None
    if TENDERSIGNAL_LLM_PROVIDER != "openai":
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("TENDERSIGNAL_ENABLE_LLM is set but OPENAI_API_KEY is missing.")
    return OpenAIEnricher()


def source_payload(opportunity: ScoredOpportunity) -> dict[str, object]:
    notice = opportunity.notice
    return {
        "title": notice.title,
        "buyer": notice.buyer,
        "country": notice.country,
        "region_city": notice.region_city,
        "deadline": notice.deadline,
        "source_url": notice.source_url,
        "cpv_codes": notice.cpv_codes,
        "document_links": notice.document_links,
        "raw_description": notice.raw_description[:3000],
        "category": opportunity.category,
        "technical_trade_relevance_score": opportunity.technical_trade_relevance_score,
        "pro_builder_relevance_score": opportunity.pro_builder_relevance_score,
        "recommended_sales_action": opportunity.recommended_sales_action,
        "evidence": opportunity.evidence,
        "uncertainties": opportunity.uncertainties,
        "account_segment": opportunity.account_segment,
        "sales_territory": opportunity.sales_territory,
        "territory_owner": opportunity.territory_owner,
        "mapping_evidence": opportunity.mapping_evidence,
    }
