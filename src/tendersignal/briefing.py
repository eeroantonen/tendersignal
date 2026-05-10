from __future__ import annotations

from tendersignal.models import ScoredOpportunity


def build_sales_briefing(opportunity: ScoredOpportunity) -> str:
    notice = opportunity.notice
    description_excerpt = notice.raw_description[:500].strip()
    if len(notice.raw_description) > 500:
        description_excerpt += "..."
    if not description_excerpt:
        description_excerpt = "No description returned by the source."

    stronger_lane = (
        "technical trade"
        if opportunity.technical_trade_relevance_score >= opportunity.pro_builder_relevance_score
        else "pro builder"
    )
    evidence = "; ".join(opportunity.evidence[:4]) or "No deterministic evidence available."
    uncertainties = "; ".join(opportunity.uncertainties[:3]) or "No major source-field uncertainties detected."
    cpv_codes = ", ".join(notice.cpv_codes[:10]) or "No CPV codes returned."
    document_links = "; ".join(notice.document_links[:5]) or "No procurement document URLs returned by source fields."
    territory = opportunity.sales_territory or "No configured territory mapping"

    return (
        f"{notice.title}\n\n"
        f"Buyer: {notice.buyer}. Country/location: {notice.country}"
        f"{' / ' + notice.region_city if notice.region_city else ''}. Deadline: {notice.deadline or 'not returned'}.\n\n"
        f"Deterministic fit: category '{opportunity.category}', stronger lane '{stronger_lane}' "
        f"(technical {opportunity.technical_trade_relevance_score:.0f}, pro builder {opportunity.pro_builder_relevance_score:.0f}).\n\n"
        f"Source description excerpt: {description_excerpt}\n\n"
        f"CPV codes: {cpv_codes}.\n\n"
        f"Document/source links: {document_links}.\n\n"
        f"Sales routing: {territory}"
        f"{' / ' + opportunity.territory_owner if opportunity.territory_owner else ''}. "
        f"{opportunity.mapping_evidence}\n\n"
        f"Recommended action: {opportunity.recommended_sales_action}\n\n"
        f"Evidence from source fields: {evidence}\n\n"
        f"Uncertainties: {uncertainties}\n\n"
        f"Source: {notice.source_url}"
    )
