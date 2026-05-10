from __future__ import annotations

from datetime import date

import pandas as pd


def buyer_options(opportunities: pd.DataFrame, awards: pd.DataFrame) -> list[str]:
    buyers = set()
    if not opportunities.empty:
        buyers.update(opportunities["buyer"].dropna().astype(str))
    if not awards.empty:
        buyers.update(awards["buyer"].dropna().astype(str))
    return sorted(buyer for buyer in buyers if buyer)


def filter_buyer_rows(df: pd.DataFrame, buyer: str) -> pd.DataFrame:
    if df.empty or not buyer:
        return df.iloc[0:0].copy()
    buyer_lc = buyer.lower()
    return df[df["buyer"].fillna("").astype(str).str.lower().str.contains(buyer_lc, regex=False)].copy()


def add_renewal_columns(awards: pd.DataFrame) -> pd.DataFrame:
    if awards.empty:
        return awards.copy()
    working = awards.copy()
    working["expiration_date"] = pd.to_datetime(working["contract_end_or_expiration"], errors="coerce", utc=True)
    today = pd.Timestamp(date.today(), tz="UTC")
    working["days_to_expiration"] = (working["expiration_date"] - today).dt.days
    working["renewal_window"] = working["days_to_expiration"].apply(renewal_window)
    return working


def renewal_window(days: float | int | None) -> str:
    if pd.isna(days):
        return "No date"
    if days < 0:
        return "Past date"
    if days <= 90:
        return "0-90 days"
    if days <= 180:
        return "91-180 days"
    if days <= 365:
        return "181-365 days"
    return "365+ days"


def buyer_360_summary(buyer: str, opportunities: pd.DataFrame, awards: pd.DataFrame) -> dict[str, object]:
    opps = filter_buyer_rows(opportunities, buyer)
    award_rows = filter_buyer_rows(awards, buyer)
    k_awards = award_rows[award_rows["match_group"] == "K Group"] if not award_rows.empty else award_rows
    competitor_awards = award_rows[award_rows["match_group"] == "Competitor"] if not award_rows.empty else award_rows
    return {
        "buyer": buyer,
        "active_opportunities": len(opps),
        "act_now": int((opps["k_priority_band"] == "Act now").sum()) if not opps.empty else 0,
        "award_rows": len(award_rows),
        "k_award_rows": len(k_awards),
        "competitor_award_rows": len(competitor_awards),
        "k_public_value": float(k_awards["amount"].sum(skipna=True)) if not k_awards.empty else 0.0,
        "competitor_public_value": float(competitor_awards["amount"].sum(skipna=True)) if not competitor_awards.empty else 0.0,
        "top_signals": top_values(opps, "strategic_demand_signal"),
        "top_lanes": top_values(opps, "k_business_lane"),
        "known_competitors": top_values(competitor_awards, "matched_supplier"),
    }


def top_values(df: pd.DataFrame, column: str, limit: int = 3) -> str:
    if df.empty or column not in df.columns:
        return "No loaded evidence"
    values = df[column].dropna().astype(str)
    if values.empty:
        return "No loaded evidence"
    return ", ".join(values.value_counts().head(limit).index)


def buyer_next_best_actions(summary: dict[str, object]) -> list[str]:
    actions = []
    if summary["act_now"]:
        actions.append("Prioritize active tender review: at least one loaded opportunity is in the Act now band.")
    if summary["competitor_award_rows"]:
        actions.append("Review competitor winner history before outreach; use public awards to understand incumbent risk.")
    if summary["k_award_rows"]:
        actions.append("Check whether Onninen/K Group public award history can support account context.")
    if summary["active_opportunities"] and not summary["award_rows"]:
        actions.append("Treat as new or unobserved buyer in loaded award history; qualify needs from source documents.")
    if not actions:
        actions.append("Monitor buyer for future notices and awards; no strong loaded signal yet.")
    return actions
