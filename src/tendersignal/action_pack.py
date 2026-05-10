from __future__ import annotations

import pandas as pd


def build_action_pack(opportunity: pd.Series, awards: pd.DataFrame) -> str:
    buyer = str(opportunity.get("buyer") or "")
    lane = str(opportunity.get("k_business_lane") or "Joint B2B opportunity")
    signal = str(opportunity.get("strategic_demand_signal") or "General construction/technical demand")
    source = str(opportunity.get("public_data_source") or opportunity.get("source_name") or "public source")
    deadline = str(opportunity.get("deadline") or "not returned")
    title = str(opportunity.get("title") or "")
    category = str(opportunity.get("category") or "")
    score = float(opportunity.get("k_priority_score") or 0)

    buyer_awards = buyer_award_context(buyer, awards)
    urgency = "today" if score >= 80 else "this week" if score >= 65 else "when capacity allows"

    return "\n".join(
        [
            f"Action pack for: {title}",
            "",
            f"1. Route {urgency}: send to {lane}. Priority score {score:.0f}; deadline {deadline}.",
            f"2. Validate scope: check lots, CPV/category fit ({category}), document links, geography and delivery requirements in {source}.",
            f"3. Positioning angle: frame the brief around {signal}. Use only the public notice description and CPV evidence.",
            f"4. Buyer context: {buyer_awards}",
            "5. Next user-ready output: create a one-page sales brief, CRM task text, and supplier/product checklist from the notice fields.",
            "",
            "Suggested CRM/task text:",
            f"Review public tender '{title}' from {buyer}. Source: {source}. Lane: {lane}. Signal: {signal}. Check documents and decide bid-support/sales follow-up before {deadline}.",
        ]
    )


def build_ready_outputs(opportunity: pd.Series, awards: pd.DataFrame) -> dict[str, str]:
    buyer = str(opportunity.get("buyer") or "")
    title = str(opportunity.get("title") or "")
    lane = str(opportunity.get("k_business_lane") or "Joint B2B opportunity")
    signal = str(opportunity.get("strategic_demand_signal") or "General construction/technical demand")
    deadline = str(opportunity.get("deadline") or "not returned")
    source_url = str(opportunity.get("source_url") or "")
    category = str(opportunity.get("category") or "")
    score = float(opportunity.get("k_priority_score") or 0)
    buyer_context = buyer_award_context(buyer, awards)

    crm_task = (
        f"Qualify public tender: {title}. Buyer: {buyer}. Lane: {lane}. "
        f"Signal: {signal}. Category: {category}. Priority score: {score:.0f}. "
        f"Deadline: {deadline}. Source: {source_url}"
    )
    sales_message = (
        f"Public procurement signal for {lane}: {buyer} has published '{title}'. "
        f"The deterministic fit is {score:.0f}/100, with demand signal '{signal}'. "
        f"Please validate the notice documents, lot structure and local delivery fit before {deadline}. "
        f"Buyer context from loaded awards: {buyer_context} Source: {source_url}"
    )
    checklist = "\n".join(
        [
            "- Confirm deadline and submission channel from the source notice.",
            "- Check lots and CPV codes against Onninen/K-Rauta Pro assortment fit.",
            "- Check geography and delivery/logistics requirements.",
            "- Review whether buyer has loaded public award history with K Group or competitors.",
            "- Decide: bid support, contractor outreach, supplier availability check, or monitor only.",
        ]
    )
    return {
        "CRM task": crm_task,
        "Sales message": sales_message,
        "Qualification checklist": checklist,
    }


def buyer_award_context(buyer: str, awards: pd.DataFrame) -> str:
    if awards.empty or not buyer:
        return "No public award history loaded for this buyer."
    buyer_lc = buyer.lower()
    matches = awards[awards["buyer"].fillna("").str.lower().str.contains(buyer_lc, regex=False)]
    if matches.empty:
        return "No matching loaded Hilma award notices for this buyer."
    k_hits = matches[matches["match_group"] == "K Group"]
    competitor_hits = matches[matches["match_group"] == "Competitor"]
    parts = [f"{len(matches)} loaded public award notice(s) for this buyer"]
    if not k_hits.empty:
        parts.append(f"{len(k_hits)} include K Group/Onninen-related winner evidence")
    if not competitor_hits.empty:
        competitors = ", ".join(sorted(set(competitor_hits["matched_supplier"].dropna()))[:5])
        parts.append(f"competitor evidence: {competitors}")
    return "; ".join(parts) + "."
