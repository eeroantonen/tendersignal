from __future__ import annotations

import re

import pandas as pd


SOURCE_LABELS = {
    "Hilma AVP-Read": "Hankintailmoitus (Hilma)",
    "TED Search API": "TED",
}

SIGNAL_RULES = (
    (
        "Energy transition / electrification",
        (
            "energy",
            "energia",
            "sähkö",
            "electric",
            "electrical",
            "charging",
            "lataus",
            "solar",
            "aurinko",
            "grid",
            "verkko",
            "lighting",
            "valaistus",
            "heat pump",
            "lämpöpumppu",
        ),
    ),
    (
        "Renovation and repair",
        (
            "renovation",
            "repair",
            "maintenance",
            "peruskorjaus",
            "korjaus",
            "ylläpito",
            "saneeraus",
            "modernisation",
            "modernisointi",
        ),
    ),
    (
        "Infrastructure and utilities",
        (
            "infrastructure",
            "infra",
            "road",
            "street",
            "water",
            "sewer",
            "district heating",
            "tie",
            "katu",
            "vesi",
            "viemäri",
            "kaukolämpö",
            "telecom",
            "fiber",
            "fibre",
        ),
    ),
    (
        "Public buildings and facilities",
        (
            "school",
            "hospital",
            "daycare",
            "building",
            "facility",
            "koulu",
            "sairaala",
            "päiväkoti",
            "kiinteistö",
            "rakennus",
        ),
    ),
    (
        "Site equipment, tools and safety",
        (
            "tool",
            "equipment",
            "machinery",
            "safety",
            "workwear",
            "työkalu",
            "laite",
            "kone",
            "turva",
            "suoja",
        ),
    ),
)


def add_business_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    working = df.copy()
    working["public_data_source"] = working["source_name"].map(SOURCE_LABELS).fillna(working["source_name"])
    working["k_business_lane"] = working.apply(k_business_lane, axis=1)
    working["k_priority_score"] = working[["technical_trade_relevance_score", "pro_builder_relevance_score"]].max(axis=1)
    working["k_priority_band"] = working["k_priority_score"].apply(priority_band)
    working["strategic_demand_signal"] = working.apply(strategic_signal, axis=1)
    working["recommended_k_action"] = working.apply(recommended_k_action, axis=1)
    return working


def k_business_lane(row: pd.Series) -> str:
    technical = float(row.get("technical_trade_relevance_score") or 0)
    builder = float(row.get("pro_builder_relevance_score") or 0)
    category = str(row.get("category") or "").lower()
    if technical >= builder + 10 or any(term in category for term in ("electrical", "hvac", "plumbing", "water systems")):
        return "Onninen technical trade"
    if builder >= technical + 10 or any(term in category for term in ("building materials", "civil works", "tools")):
        return "K-Rauta Pro builder retail"
    return "Joint B2B opportunity"


def priority_band(score: float) -> str:
    if score >= 80:
        return "Act now"
    if score >= 65:
        return "Qualify"
    if score >= 45:
        return "Monitor"
    return "Low fit"


def strategic_signal(row: pd.Series) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in ("title", "raw_description", "category", "cpv_codes")
    ).lower()
    for label, keywords in SIGNAL_RULES:
        if any(keyword in text for keyword in keywords):
            return label
    return "General construction/technical demand"


def recommended_k_action(row: pd.Series) -> str:
    band = row.get("k_priority_band", "Monitor")
    lane = row.get("k_business_lane", "Joint B2B opportunity")
    signal = row.get("strategic_demand_signal", "General construction/technical demand")
    source = row.get("public_data_source", "public source")
    if band == "Act now":
        return f"Route to {lane}; validate lots and document links from {source}; prepare buyer contact brief around {signal}."
    if band == "Qualify":
        return f"Ask {lane} owner to qualify fit this week; check geography, contractor ecosystem and product availability."
    if band == "Monitor":
        return f"Keep in analyst watchlist; use if the buyer repeats or the category signal strengthens."
    return "Keep for demand sensing only unless a local sales team recognizes the buyer."


def source_filter_options() -> list[str]:
    return ["Both sources", "Hankintailmoitus (Hilma)", "TED"]


def apply_source_filter(df: pd.DataFrame, selected: str) -> pd.DataFrame:
    if df.empty or selected == "Both sources":
        return df
    return df[df["public_data_source"] == selected].copy()


def source_badge(source_name: str) -> str:
    return SOURCE_LABELS.get(source_name, source_name)


def safe_contains(text: str, pattern: str) -> bool:
    return bool(re.search(re.escape(pattern), text, flags=re.IGNORECASE))
