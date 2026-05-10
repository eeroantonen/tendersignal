from __future__ import annotations

import pandas as pd


QUESTIONS = [
    "Summarize for Onninen sales",
    "Summarize for K-Rauta Pro",
    "What should we check before acting?",
    "What product families might be relevant?",
    "What is uncertain?",
    "Draft a short buyer outreach note",
]

PRODUCT_FAMILIES = {
    "Electrical, telecom and lighting": [
        "electrical supplies",
        "cabling and connectivity",
        "lighting",
        "building automation or telecom components",
    ],
    "HVAC, plumbing and water systems": [
        "HVAC components",
        "pipes, valves and fittings",
        "pumps and water treatment components",
        "maintenance and technical service parts",
    ],
    "Building materials and structural works": [
        "building materials",
        "timber, boards and insulation",
        "doors, windows and roofing materials",
        "fasteners and construction consumables",
    ],
    "Civil works and site infrastructure": [
        "civil works materials",
        "pipes and drainage",
        "site supplies",
        "tools and consumables for contractors",
    ],
    "Tools, machinery and site equipment": [
        "tools",
        "site equipment",
        "safety products",
        "workwear and consumables",
    ],
}


def answer_question(row: pd.Series, awards: pd.DataFrame, question: str) -> str:
    if question == "Summarize for Onninen sales":
        return summarize_for_lane(row, "Onninen technical trade")
    if question == "Summarize for K-Rauta Pro":
        return summarize_for_lane(row, "K-Rauta Pro builder retail")
    if question == "What should we check before acting?":
        return checks(row)
    if question == "What product families might be relevant?":
        return product_families(row)
    if question == "What is uncertain?":
        return uncertainties(row)
    if question == "Draft a short buyer outreach note":
        return outreach_note(row)
    return "Choose a supported question."


def summarize_for_lane(row: pd.Series, lane: str) -> str:
    score = row.get("technical_trade_relevance_score") if "Onninen" in lane else row.get("pro_builder_relevance_score")
    return (
        f"{row.get('title')} is a public notice from {row.get('buyer')} in {row.get('public_data_source')}. "
        f"For {lane}, the deterministic relevance score is {float(score or 0):.0f}/100. "
        f"The notice is categorized as {row.get('category')} with demand signal {row.get('strategic_demand_signal')}. "
        f"Deadline from source: {row.get('deadline') or 'not returned'}. "
        f"Use the source notice to validate lots, documents, geography and submission requirements."
    )


def checks(row: pd.Series) -> str:
    return "\n".join(
        [
            "Check these before acting:",
            f"- Source notice and documents: {row.get('source_url')}",
            f"- Deadline and submission channel: {row.get('deadline') or 'not returned'}",
            f"- CPV/category evidence: {row.get('cpv_codes') or 'not returned'} / {row.get('category')}",
            f"- Buyer and region: {row.get('buyer')} / {row.get('region_city') or 'not returned'}",
            "- Whether this is direct supply, contractor-support opportunity, or only demand sensing.",
            "- Whether account/territory mapping should be added for this buyer.",
        ]
    )


def product_families(row: pd.Series) -> str:
    category = str(row.get("category") or "")
    families = PRODUCT_FAMILIES.get(category, ["public notice category is too broad; validate source documents first"])
    return (
        "Possible product-family checklist, derived from category and CPV evidence, not from hidden tender documents:\n"
        + "\n".join(f"- {family}" for family in families)
    )


def uncertainties(row: pd.Series) -> str:
    uncertainty_text = str(row.get("uncertainties") or "").strip()
    if not uncertainty_text:
        return "No stored uncertainty text was found, but the user should still validate the source notice before action."
    return f"Stored deterministic uncertainties:\n{uncertainty_text}"


def outreach_note(row: pd.Series) -> str:
    return (
        f"Hello, we noticed the public procurement notice '{row.get('title')}' from {row.get('buyer')}. "
        f"Based on the public notice category ({row.get('category')}), our team would like to review whether "
        f"there is a relevant technical trade or professional builder supply need before the deadline "
        f"({row.get('deadline') or 'not returned'}). We will use the official notice documents as the source of truth."
    )
