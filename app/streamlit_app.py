from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from tendersignal.action_pack import build_action_pack, build_ready_outputs
from tendersignal.awards import load_awards_dataframe, run_hilma_award_ingestion
from tendersignal.business import add_business_columns, apply_source_filter, source_filter_options
from tendersignal.buyer_intel import (
    add_renewal_columns,
    buyer_360_summary,
    buyer_next_best_actions,
    filter_buyer_rows,
)
from tendersignal.config import CACHE_DIR, DEFAULT_DB_PATH
from tendersignal.database import init_db, load_ingestion_runs, load_opportunities
from tendersignal.export import EXPORT_COLUMNS, export_csv, opportunities_dataframe
from tendersignal.geo import CITY_CENTROIDS, extract_city_from_award_row, extract_city_from_notice_row
from tendersignal.llm.action_drafter import maybe_polish_action_outputs
from tendersignal.pipeline import (
    run_hilma_ingestion,
    run_hilma_ingestion_for_period,
    run_ingestion,
    run_ted_ingestion_for_period,
)
from tendersignal.tender_agent import QUESTIONS, answer_question

st.set_page_config(page_title="TenderSignal", page_icon="TS", layout="wide")


def configure_streamlit_secrets() -> None:
    try:
        key = st.secrets.get("HILMA_AVP_SUBSCRIPTION_KEY", "")
    except Exception:
        key = ""
    if key and not os.environ.get("HILMA_AVP_SUBSCRIPTION_KEY"):
        os.environ["HILMA_AVP_SUBSCRIPTION_KEY"] = str(key)


configure_streamlit_secrets()


PAGES = [
    "K business radar",
    "Opportunity map",
    "Award & competitor intelligence",
    "Buyer 360",
    "Today's opportunities",
    "Category pipeline",
    "Notice detail / sales brief",
    "Data reliability",
    "Export",
]

PAGE_GUIDANCE = {
    "K business radar": {
        "use": "Executive triage page for seeing which public notices deserve commercial attention first.",
        "who": "Sales management, category leads, senior analysts, and business development leads.",
        "benefit": "Turns thousands of TED/Hilma notices into a prioritized K-Rauta Pro, Onninen, or joint B2B action queue.",
        "next": "Pick the Act now rows, validate source documents, assign the lane owner, and move qualified cases into CRM.",
    },
    "Opportunity map": {
        "use": "City-level geographic demand view for seeing where active opportunities and public value signals cluster.",
        "who": "Regional sales leads, territory planning, category managers, and interview stakeholders who need the big picture fast.",
        "benefit": "Shows where demand is concentrated without inventing exact addresses or tender values that the source did not return.",
        "next": "Use high-count cities to focus account review, then open the underlying notices before contacting buyers.",
    },
    "Award & competitor intelligence": {
        "use": "Market-position page for public Hilma award evidence involving K Group/Onninen and selected competitors.",
        "who": "Commercial analysts, sales directors, account owners, and sourcing/category teams.",
        "benefit": "Separates K public award signals from competitor award signals and shows public framework values where Hilma provides them.",
        "next": "Review competitor buyers, check renewal windows, and decide which accounts need proactive relationship work.",
    },
    "Buyer 360": {
        "use": "Single-buyer account intelligence page combining active opportunities and public award history.",
        "who": "Named account managers, regional sales, analyst support, and bid/no-bid reviewers.",
        "benefit": "Gives one buyer view: active opportunities, known public competitors, public value context, and next-best actions.",
        "next": "Select a buyer, review current opportunities, check competitor/K award history, and prepare the contact plan.",
    },
    "Today's opportunities": {
        "use": "Daily operating queue for new or latest public procurement opportunities.",
        "who": "Sales operations, inside sales, analyst duty desk, and category owners.",
        "benefit": "Provides a repeatable morning review list with scores, lanes, actions, and source links.",
        "next": "Review the high-fit rows, confirm deadlines/documents, and route to the correct sales or category owner.",
    },
    "Category pipeline": {
        "use": "Portfolio view for understanding which categories are building in the public procurement pipeline.",
        "who": "Category management, procurement analytics, assortment planning, and senior commercial leadership.",
        "benefit": "Highlights where demand is clustering across electrical, HVAC, building materials, civil works, and tools/site equipment.",
        "next": "Compare category demand with inventory, supplier campaigns, and sales focus areas.",
    },
    "Notice detail / sales brief": {
        "use": "Source-grounded deep dive for one tender notice and its sales action pack.",
        "who": "Account managers, bid support, sales engineers, analysts, and category specialists.",
        "benefit": "Explains why the notice was scored, what is uncertain, and produces CRM/email/checklist drafts without hallucinated facts.",
        "next": "Open the source notice, inspect documents, complete the qualification checklist, and decide owner/action.",
    },
    "Data reliability": {
        "use": "Audit and trust page for ingestion history, field completeness, and known limitations.",
        "who": "Senior analysts, data owners, interview evaluators, and anyone challenging data quality.",
        "benefit": "Makes failures, missing fields, and source limitations visible instead of hiding them behind polished UI.",
        "next": "Check failed runs, field gaps, and whether missing source fields require process changes or source-specific logic.",
    },
    "Export": {
        "use": "Operational handoff page for producing CSVs for Excel, CRM import, or stakeholder review.",
        "who": "Sales operations, analysts, CRM/data users, and managers who need a portable worklist.",
        "benefit": "Turns the filtered scored opportunity set into a file that can be shared or loaded into downstream tools.",
        "next": "Create the export, review columns, then hand the filtered list to owners or import it into the next workflow.",
    },
}

VALUE_KEYS = (
    "estimatedValue",
    "overallMaximumFrameworkContractsAmount",
    "overallApproximateFrameworkContractsAmount",
    "noticeResultTotalAmount",
)


@st.cache_data(ttl=60)
def cached_dataframe(db_path: str, db_version: int) -> pd.DataFrame:
    _ = db_version
    return add_opportunity_geo_columns(opportunities_dataframe(Path(db_path)))


@st.cache_data(ttl=60)
def cached_awards_dataframe(db_path: str, db_version: int) -> pd.DataFrame:
    _ = db_version
    return add_award_geo_columns(load_awards_dataframe(Path(db_path)))


def refresh_data() -> None:
    cached_dataframe.clear()
    cached_awards_dataframe.clear()


def cached_public_data_available() -> bool:
    return (
        (CACHE_DIR / "ted_notices_sample.json").exists()
        and (CACHE_DIR / "hilma_notices_sample.json").exists()
        and (CACHE_DIR / "hilma_awards_sample.json").exists()
    )


def seed_database_from_public_cache(db_path: Path) -> list[str]:
    init_db(db_path)
    if load_opportunities(db_path):
        return []
    if not cached_public_data_available():
        return ["No existing database and bundled public cache is incomplete."]
    messages = []
    ted_count = run_ingestion(db_path, use_cache=True)
    messages.append(f"Loaded {ted_count} cached TED notices.")
    hilma_count = run_hilma_ingestion(db_path, use_cache=True)
    messages.append(f"Loaded {hilma_count} cached Hilma notices.")
    award_count = run_hilma_award_ingestion(db_path, use_cache=True)
    messages.append(f"Loaded {award_count} cached Hilma award notices.")
    refresh_data()
    return messages


def parse_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return [item.strip() for item in str(value).split("|") if item.strip()]


def add_opportunity_geo_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "map_city" in df.columns:
        return df.copy()
    working = df.copy()
    city_matches = working.apply(extract_city_from_notice_row, axis=1)
    working["map_city"] = city_matches.apply(lambda item: item[0])
    working["city_evidence"] = city_matches.apply(lambda item: item[1])
    working["notice_value_eur"] = working.apply(extract_notice_value_eur, axis=1)
    return working


def add_award_geo_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "map_city" in df.columns:
        return df.copy()
    working = df.copy()
    city_matches = working.apply(extract_city_from_award_row, axis=1)
    working["map_city"] = city_matches.apply(lambda item: item[0])
    return working


def score_band(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    return "Low"


def show_navigation() -> str:
    with st.sidebar:
        st.header("TenderSignal")
        return st.selectbox("Page", PAGES)


def show_page_guide(page: str) -> None:
    guidance = PAGE_GUIDANCE[page]
    with st.expander("How to use this page", expanded=True):
        cols = st.columns(4)
        cols[0].markdown(f"**Used for**\n\n{guidance['use']}")
        cols[1].markdown(f"**Used by**\n\n{guidance['who']}")
        cols[2].markdown(f"**Benefit**\n\n{guidance['benefit']}")
        cols[3].markdown(f"**Next steps**\n\n{guidance['next']}")


def show_ingest_controls(db_path: Path) -> str:
    with st.sidebar:
        st.caption("Real TED and Hankintailmoitus/Hilma public procurement data. Deterministic MVP, no LLM by default.")
        source_filter = st.selectbox("Analyze source", source_filter_options())
        source = st.selectbox("Ingest source", ["Hilma AVP-Read", "TED Search API"])
        days_back = st.slider("Publication window, days", min_value=3, max_value=90, value=21)
        limit = st.slider("Max notices", min_value=10, max_value=250, value=100, step=10)
        key_available = bool(os.environ.get("HILMA_AVP_SUBSCRIPTION_KEY"))
        use_cache = st.toggle("Use cached sample", value=not key_available)
        hilma_cache_available = (CACHE_DIR / "hilma_notices_sample.json").exists()
        award_cache_available = (CACHE_DIR / "hilma_awards_sample.json").exists()
        st.caption(
            "Hilma live API: configured"
            if key_available
            else "Hosted/cache mode: Hilma key is not configured, so live Hilma refresh is disabled."
        )
        if st.button("Ingest notices", type="primary", width="stretch"):
            try:
                if source == "Hilma AVP-Read" and not key_available and not use_cache:
                    raise RuntimeError(
                        "Hilma live ingestion needs HILMA_AVP_SUBSCRIPTION_KEY in the Streamlit server environment. "
                        "Turn on 'Use cached sample' or restart Streamlit with the key."
                    )
                with st.spinner("Fetching and scoring real public notices..."):
                    if source == "Hilma AVP-Read":
                        count = run_hilma_ingestion(db_path, days_back=days_back, limit=limit, use_cache=use_cache)
                    else:
                        count = run_ingestion(db_path, days_back=days_back, limit=limit, use_cache=use_cache)
                refresh_data()
                st.success(f"Ingested {count} notices.")
            except Exception as exc:
                st.error(f"Ingestion failed clearly: {exc}")
        if st.button("Ingest Hilma award intelligence", width="stretch"):
            try:
                award_use_cache = use_cache or not key_available
                if award_use_cache and not award_cache_available:
                    raise RuntimeError(
                        "No cached Hilma award sample is available and the live API key is not visible to Streamlit."
                    )
                with st.spinner("Fetching public Hilma award notices..."):
                    count = run_hilma_award_ingestion(db_path, use_cache=award_use_cache)
                refresh_data()
                source_text = "cached" if award_use_cache else "live"
                st.success(f"Ingested {count} {source_text} award notices.")
            except Exception as exc:
                st.error(f"Award ingestion failed clearly: {exc}")
        if st.button("Refresh 2026 YTD", width="stretch", disabled=not key_available):
            try:
                if not key_available:
                    raise RuntimeError(
                        "Full 2026 refresh needs HILMA_AVP_SUBSCRIPTION_KEY in the Streamlit server environment. "
                        "TED can still be refreshed from the command line, but this button refreshes TED and Hilma together."
                    )
                with st.spinner("Refreshing all 2026 year-to-date notices from TED and Hilma..."):
                    start = date(2026, 1, 1)
                    end = date(2027, 1, 1)
                    ted_count = run_ted_ingestion_for_period(db_path, start, end, limit=10000)
                    hilma_count = run_hilma_ingestion_for_period(
                        db_path,
                        start,
                        end,
                        limit=10000,
                        include_expired=True,
                    )
                    award_count = run_hilma_award_ingestion(db_path, days_back=1460)
                refresh_data()
                st.success(
                    f"Refreshed 2026 YTD: {ted_count} TED notices, "
                    f"{hilma_count} Hilma notices, {award_count} award rows fetched."
                )
            except Exception as exc:
                st.error(f"2026 refresh failed clearly: {exc}")
        if not key_available:
            st.info(
                "Recruiter-friendly hosted mode uses the bundled real public cache. "
                "Configure HILMA_AVP_SUBSCRIPTION_KEY only when you want live Hilma refresh."
            )
        if source == "Hilma AVP-Read" and not key_available and hilma_cache_available:
            st.caption("Tip: turn on 'Use cached sample' to reload the real Hilma sample already saved in data/cache.")
        return source_filter


def apply_publication_date_filter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    working = df.copy()
    date_text = working["publication_date"].fillna("").astype(str)
    date_prefix = date_text.str.extract(r"(\d{4}-\d{2}-\d{2})", expand=False)
    parsed = pd.to_datetime(date_prefix.fillna(date_text), errors="coerce", utc=True)
    available = parsed.dropna()
    if available.empty:
        return working
    min_date = available.min().date()
    max_date = available.max().date()
    default_start = max(min_date, date(2026, 1, 1))
    default_end = max_date
    with st.sidebar:
        selected_range = st.date_input(
            "Publication date range",
            value=(default_start, default_end),
            min_value=min_date,
            max_value=max_date,
        )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start, end = selected_range
        mask = parsed.dt.date.ge(start) & parsed.dt.date.le(end)
        return working[mask].copy()
    return working


def show_business_radar(df: pd.DataFrame) -> None:
    st.title("K Business Radar")
    show_page_guide("K business radar")
    if df.empty:
        st.info("No notices match the selected source filter.")
        return

    working = df.copy()
    metric_cols = st.columns(5)
    metric_cols[0].metric("Notices", len(working))
    metric_cols[1].metric("Act now", int((working["k_priority_band"] == "Act now").sum()))
    metric_cols[2].metric("Hilma share", f"{(working['public_data_source'].eq('Hankintailmoitus (Hilma)').mean() * 100):.0f}%")
    metric_cols[3].metric("Onninen lane", int((working["k_business_lane"] == "Onninen technical trade").sum()))
    metric_cols[4].metric("K-Rauta Pro lane", int((working["k_business_lane"] == "K-Rauta Pro builder retail").sum()))

    st.subheader("Sales Action Queue")
    queue = working.sort_values(["k_priority_score", "deadline"], ascending=[False, True]).head(25)
    st.dataframe(
        queue[
            [
                "public_data_source",
                "k_business_lane",
                "k_priority_band",
                "k_priority_score",
                "strategic_demand_signal",
                "title",
                "buyer",
                "deadline",
                "recommended_k_action",
                "source_url",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={"source_url": st.column_config.LinkColumn("Source")},
    )

    cols = st.columns(2)
    with cols[0]:
        st.subheader("Demand Signals")
        signal_counts = working.groupby("strategic_demand_signal")["title"].count().sort_values(ascending=False)
        st.bar_chart(signal_counts)
    with cols[1]:
        st.subheader("Business Lanes")
        lane_counts = working.groupby("k_business_lane")["title"].count().sort_values(ascending=False)
        st.bar_chart(lane_counts)

    st.subheader("Buyer Intelligence")
    buyer_summary = (
        working.groupby(["buyer", "public_data_source"], as_index=False)
        .agg(
            notices=("title", "count"),
            avg_priority=("k_priority_score", "mean"),
            first_deadline=("deadline", "min"),
            lanes=("k_business_lane", lambda values: ", ".join(sorted(set(values)))),
            signals=("strategic_demand_signal", lambda values: ", ".join(sorted(set(values))[:3])),
        )
        .sort_values(["notices", "avg_priority"], ascending=False)
        .head(30)
    )
    st.dataframe(buyer_summary, hide_index=True, width="stretch")


def extract_notice_value_eur(row: pd.Series) -> float | None:
    source_name = str(row.get("source_name") or row.get("public_data_source") or "")
    if "Hilma" not in source_name and "Hankintailmoitus" not in source_name:
        return None
    try:
        raw = json.loads(row.get("raw_notice") or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    for key in VALUE_KEYS:
        value = raw.get(key)
        if isinstance(value, list):
            value = next((item for item in value if item not in (None, "")), None)
        if isinstance(value, dict):
            value = next((item for item in value.values() if item not in (None, "")), None)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            return numeric
    return None


def lane_color(lane: str) -> tuple[int, int, int]:
    if lane == "Onninen technical trade":
        return (24, 122, 92)
    if lane == "K-Rauta Pro builder retail":
        return (204, 79, 38)
    return (53, 95, 150)


def show_opportunity_map(df: pd.DataFrame, awards: pd.DataFrame) -> None:
    st.title("Opportunity Map")
    show_page_guide("Opportunity map")
    if df.empty:
        st.info("No opportunities match the selected source and date filters.")
        return

    working = df.copy()
    working = working[working["map_city"].isin(CITY_CENTROIDS)].copy()
    if working.empty:
        st.info("No city names were found in the selected source fields. The map only plots source-grounded city matches.")
        return

    working["is_act_now"] = working["k_priority_band"].eq("Act now")
    city_rows = (
        working.groupby("map_city", as_index=False)
        .agg(
            opportunities=("title", "count"),
            act_now=("is_act_now", "sum"),
            avg_priority=("k_priority_score", "mean"),
            opportunity_value_eur=("notice_value_eur", "sum"),
            value_rows=("notice_value_eur", lambda values: int(values.notna().sum())),
            top_lane=("k_business_lane", lambda values: values.value_counts().index[0]),
            top_signal=("strategic_demand_signal", lambda values: values.value_counts().index[0]),
        )
    )

    award_summary = pd.DataFrame(columns=["map_city", "public_award_value_eur", "award_rows"])
    if not awards.empty:
        award_working = awards.copy()
        award_working = award_working[award_working["map_city"].isin(CITY_CENTROIDS)].copy()
        if not award_working.empty:
            award_summary = (
                award_working.groupby("map_city", as_index=False)
                .agg(public_award_value_eur=("amount", "sum"), award_rows=("title", "count"))
            )

    map_df = city_rows.merge(award_summary, on="map_city", how="left")
    map_df["public_award_value_eur"] = map_df["public_award_value_eur"].fillna(0.0)
    map_df["award_rows"] = map_df["award_rows"].fillna(0).astype(int)
    map_df["lat"] = map_df["map_city"].map(lambda city: CITY_CENTROIDS[city]["lat"])
    map_df["lon"] = map_df["map_city"].map(lambda city: CITY_CENTROIDS[city]["lon"])
    map_df["country_code"] = map_df["map_city"].map(lambda city: CITY_CENTROIDS[city]["country"])
    map_df["value_coverage"] = (map_df["value_rows"] / map_df["opportunities"] * 100).round(1)
    map_df["dot_radius_m"] = 24000
    colors = map_df["top_lane"].apply(lane_color)
    map_df["color_r"] = colors.apply(lambda item: item[0])
    map_df["color_g"] = colors.apply(lambda item: item[1])
    map_df["color_b"] = colors.apply(lambda item: item[2])

    metric_cols = st.columns(4)
    metric_cols[0].metric("Mapped opportunities", int(map_df["opportunities"].sum()))
    metric_cols[1].metric("Act now", int(map_df["act_now"].sum()))
    metric_cols[2].metric("Active value coverage", f"{(working['notice_value_eur'].notna().mean() * 100):.1f}%")
    metric_cols[3].metric("Public award value", f"€{map_df['public_award_value_eur'].sum()/1_000_000:.1f}m")

    st.caption(
        "Map dots use city names found in public source fields and static city centroids. "
        "Dot size is fixed so geography is not distorted. "
        "Active opportunity value is shown only when the notice payload includes a public amount field. "
        "Public award value is Hilma award/framework context, not expected revenue."
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius="dot_radius_m",
        get_fill_color="[color_r, color_g, color_b, 170]",
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )
    view_state = pdk.ViewState(latitude=60.7, longitude=22.0, zoom=4.2, pitch=25)
    tooltip = {
        "html": (
            "<b>{map_city}</b><br/>"
            "Country: {country_code}<br/>"
            "Opportunities: {opportunities}<br/>"
            "Act now: {act_now}<br/>"
            "Top lane: {top_lane}<br/>"
            "Active public value: €{opportunity_value_eur}<br/>"
            "Hilma award value context: €{public_award_value_eur}<br/>"
            "Value coverage: {value_coverage}%"
        ),
        "style": {"backgroundColor": "#1f2933", "color": "white"},
    }
    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=view_state,
            layers=[layer],
            tooltip=tooltip,
        ),
        height=520,
    )

    st.subheader("Map Data")
    display = map_df[
        [
            "map_city",
            "country_code",
            "opportunities",
            "act_now",
            "avg_priority",
            "top_lane",
            "top_signal",
            "opportunity_value_eur",
            "value_rows",
            "value_coverage",
            "public_award_value_eur",
            "award_rows",
        ]
    ].sort_values(["opportunities", "public_award_value_eur"], ascending=False)
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "avg_priority": st.column_config.NumberColumn("Avg priority", format="%.1f"),
            "opportunity_value_eur": st.column_config.NumberColumn("Active public value EUR", format="€%.0f"),
            "public_award_value_eur": st.column_config.NumberColumn("Hilma award value EUR", format="€%.0f"),
            "value_coverage": st.column_config.NumberColumn("Value coverage %", format="%.1f"),
        },
    )

    st.subheader("Highest Priority City-Mapped Opportunities")
    st.dataframe(
        working[
            [
                "public_data_source",
                "map_city",
                "city_evidence",
                "country",
                "region_city",
                "k_business_lane",
                "k_priority_band",
                "k_priority_score",
                "title",
                "buyer",
                "deadline",
                "notice_value_eur",
                "source_url",
            ]
        ]
        .sort_values(["k_priority_score", "deadline"], ascending=[False, True])
        .head(40),
        hide_index=True,
        width="stretch",
        column_config={
            "source_url": st.column_config.LinkColumn("Source"),
            "notice_value_eur": st.column_config.NumberColumn("Public notice value EUR", format="€%.0f"),
        },
    )


def show_award_intelligence(awards: pd.DataFrame) -> None:
    st.title("Award & Competitor Intelligence")
    show_page_guide("Award & competitor intelligence")
    if awards.empty:
        st.info("No Hilma award intelligence loaded yet. Use the sidebar button to ingest public award notices.")
        return

    working = awards.copy()
    amount_df = working[working["amount"].notna()]
    k_awards = working[working["match_group"] == "K Group"]
    competitor_awards = working[working["match_group"] == "Competitor"]
    k_amount = k_awards["amount"].sum(skipna=True)
    competitor_amount = competitor_awards["amount"].sum(skipna=True)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Award rows", len(working))
    metric_cols[1].metric("K Group rows", len(k_awards))
    metric_cols[2].metric("Competitor rows", len(competitor_awards))
    metric_cols[3].metric("K public value", f"€{k_amount/1_000_000:.1f}m")
    metric_cols[4].metric("Amount coverage", f"{(len(amount_df) / len(working) * 100):.0f}%")

    st.caption(
        "Values are public notice/framework amounts where Hilma provides them, not realized sales. "
        "Rows can include multiple suppliers from the same framework award."
    )

    cols = st.columns(2)
    with cols[0]:
        st.subheader("Supplier Benchmark")
        supplier_summary = (
            working.groupby(["match_group", "matched_supplier"], as_index=False)
            .agg(
                award_rows=("title", "count"),
                public_value_eur=("amount", "sum"),
                buyers=("buyer", lambda values: len(set(values))),
            )
            .sort_values(["match_group", "public_value_eur", "award_rows"], ascending=[True, False, False])
        )
        st.dataframe(supplier_summary, hide_index=True, width="stretch")
    with cols[1]:
        st.subheader("Direct Value Signal")
        value_by_group = (
            working.groupby("match_group")["amount"]
            .sum()
            .sort_values(ascending=False)
        )
        st.bar_chart(value_by_group)

    st.subheader("K Group / Onninen Public Awards")
    st.dataframe(
        k_awards[
            [
                "publication_date",
                "notice_number",
                "title",
                "buyer",
                "matched_supplier",
                "amount",
                "currency",
                "contract_end_or_expiration",
                "source_url",
            ]
        ].head(50),
        hide_index=True,
        width="stretch",
        column_config={"source_url": st.column_config.LinkColumn("Source")},
    )

    st.subheader("Competitor Watch")
    st.dataframe(
        competitor_awards[
            [
                "publication_date",
                "notice_number",
                "title",
                "buyer",
                "matched_supplier",
                "amount",
                "currency",
                "contract_end_or_expiration",
                "source_url",
            ]
        ].head(75),
        hide_index=True,
        width="stretch",
        column_config={"source_url": st.column_config.LinkColumn("Source")},
    )

    st.subheader("Renewal Watch")
    renewal = add_renewal_columns(working)
    renewal = renewal[renewal["contract_end_or_expiration"].fillna("").astype(str).str.len().gt(0)].copy()
    if renewal.empty:
        st.write("No contract end or expiration fields available in the loaded award notices.")
    else:
        renewal_filter = st.selectbox("Renewal window", ["All", "0-90 days", "91-180 days", "181-365 days", "365+ days", "Past date", "No date"])
        if renewal_filter != "All":
            renewal = renewal[renewal["renewal_window"] == renewal_filter]
        st.dataframe(
            renewal[
                [
                    "renewal_window",
                    "days_to_expiration",
                    "contract_end_or_expiration",
                    "title",
                    "buyer",
                    "matched_supplier",
                    "match_group",
                    "amount",
                    "currency",
                    "source_url",
                ]
            ].sort_values("contract_end_or_expiration").head(50),
            hide_index=True,
            width="stretch",
            column_config={"source_url": st.column_config.LinkColumn("Source")},
        )


def buyer_ranking_dataframe(opportunities: pd.DataFrame, awards: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not opportunities.empty:
        opps = opportunities.copy()
        if "notice_value_eur" not in opps.columns:
            opps["notice_value_eur"] = opps.apply(extract_notice_value_eur, axis=1)
        frames.append(
            opps.groupby("buyer", as_index=False).agg(
                active_opportunities=("title", "count"),
                act_now=("k_priority_band", lambda values: int((values == "Act now").sum())),
                avg_priority=("k_priority_score", "mean"),
                active_public_value_eur=("notice_value_eur", "sum"),
                active_value_rows=("notice_value_eur", lambda values: int(values.notna().sum())),
            )
        )
    if not awards.empty:
        frames.append(
            awards.groupby("buyer", as_index=False).agg(
                award_rows=("title", "count"),
                public_award_value_eur=("amount", "sum"),
            )
        )
    if not frames:
        return pd.DataFrame()
    ranking = frames[0]
    for frame in frames[1:]:
        ranking = ranking.merge(frame, on="buyer", how="outer")
    numeric_columns = [
        "active_opportunities",
        "act_now",
        "avg_priority",
        "active_public_value_eur",
        "active_value_rows",
        "award_rows",
        "public_award_value_eur",
    ]
    for column in numeric_columns:
        if column not in ranking.columns:
            ranking[column] = 0
        ranking[column] = pd.to_numeric(ranking[column], errors="coerce").fillna(0)
    ranking["total_public_value_eur"] = ranking["active_public_value_eur"] + ranking["public_award_value_eur"]
    ranking["buyer_label"] = ranking.apply(
        lambda row: (
            f"{row['buyer']} | value €{row['total_public_value_eur']/1_000_000:.1f}m | "
            f"active {int(row['active_opportunities'])} | awards {int(row['award_rows'])}"
        ),
        axis=1,
    )
    return ranking.sort_values(
        ["total_public_value_eur", "act_now", "active_opportunities", "avg_priority"],
        ascending=[False, False, False, False],
    )


def show_buyer_360(opportunities: pd.DataFrame, awards: pd.DataFrame) -> None:
    st.title("Buyer 360")
    show_page_guide("Buyer 360")
    ranking = buyer_ranking_dataframe(opportunities, awards)
    if ranking.empty:
        st.info("No buyer data loaded yet.")
        return
    st.caption("Click the buyer selector and type to search. Buyers are ranked by public value, then Act now count and active opportunity volume.")
    selected_label = st.selectbox("Search and select buyer ranked by public value", ranking["buyer_label"].head(500).tolist())
    selected_buyer = selected_label.split(" | value ", 1)[0]

    with st.expander("Buyer ranking", expanded=False):
        st.caption(
            "Ranking sorts by public value first. Active tender value is included only when the notice payload has a public amount field; "
            "award value comes from public Hilma award/framework fields."
        )
        st.dataframe(
            ranking[
                [
                    "buyer",
                    "total_public_value_eur",
                    "public_award_value_eur",
                    "active_public_value_eur",
                    "active_value_rows",
                    "active_opportunities",
                    "act_now",
                    "award_rows",
                    "avg_priority",
                ]
            ].head(100),
            hide_index=True,
            width="stretch",
            column_config={
                "total_public_value_eur": st.column_config.NumberColumn("Total public value EUR", format="€%.0f"),
                "public_award_value_eur": st.column_config.NumberColumn("Award value EUR", format="€%.0f"),
                "active_public_value_eur": st.column_config.NumberColumn("Active notice value EUR", format="€%.0f"),
                "avg_priority": st.column_config.NumberColumn("Avg priority", format="%.1f"),
            },
        )

    opps = filter_buyer_rows(opportunities, selected_buyer)
    award_rows = add_renewal_columns(filter_buyer_rows(awards, selected_buyer))
    summary = buyer_360_summary(selected_buyer, opportunities, awards)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Active opportunities", summary["active_opportunities"])
    metric_cols[1].metric("Act now", summary["act_now"])
    metric_cols[2].metric("Award rows", summary["award_rows"])
    metric_cols[3].metric("K public value", f"€{summary['k_public_value']/1_000_000:.1f}m")
    metric_cols[4].metric("Competitor value", f"€{summary['competitor_public_value']/1_000_000:.1f}m")

    cols = st.columns([1, 1])
    with cols[0]:
        st.subheader("Buyer Signals")
        st.write(f"**Top demand signals:** {summary['top_signals']}")
        st.write(f"**Business lanes:** {summary['top_lanes']}")
        st.write(f"**Known competitors:** {summary['known_competitors']}")
    with cols[1]:
        st.subheader("Next Best Actions")
        for action in buyer_next_best_actions(summary):
            st.write(f"- {action}")

    st.subheader("Active Opportunities")
    if opps.empty:
        st.write("No active opportunities for this buyer in the selected source filter.")
    else:
        st.dataframe(
            opps[
                [
                    "public_data_source",
                    "k_business_lane",
                    "k_priority_band",
                    "k_priority_score",
                    "strategic_demand_signal",
                    "title",
                    "deadline",
                    "source_url",
                ]
            ].sort_values(["k_priority_score", "deadline"], ascending=[False, True]),
            hide_index=True,
            width="stretch",
            column_config={"source_url": st.column_config.LinkColumn("Source")},
        )

    st.subheader("Public Award History")
    if award_rows.empty:
        st.write("No loaded public award rows for this buyer.")
    else:
        st.dataframe(
            award_rows[
                [
                    "publication_date",
                    "renewal_window",
                    "title",
                    "matched_supplier",
                    "match_group",
                    "amount",
                    "currency",
                    "contract_end_or_expiration",
                    "source_url",
                ]
            ].sort_values("publication_date", ascending=False),
            hide_index=True,
            width="stretch",
            column_config={"source_url": st.column_config.LinkColumn("Source")},
        )


def show_today(df: pd.DataFrame) -> None:
    st.title("Today's Opportunities")
    show_page_guide("Today's opportunities")
    if df.empty:
        st.info("No opportunities in the database yet. Run ingestion from the sidebar.")
        return

    today_iso = date.today().isoformat()
    working = df.copy()
    working["best_score"] = working[["technical_trade_relevance_score", "pro_builder_relevance_score"]].max(axis=1)
    today_df = working[working["publication_date"].astype(str).str.startswith(today_iso)]
    display_df = today_df if not today_df.empty else working.head(50)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Displayed notices", len(display_df))
    metric_cols[1].metric("High fit", int((display_df["best_score"] >= 75).sum()))
    metric_cols[2].metric("Technical avg", f"{display_df['technical_trade_relevance_score'].mean():.0f}")
    metric_cols[3].metric("Builder avg", f"{display_df['pro_builder_relevance_score'].mean():.0f}")

    st.dataframe(
        display_df[
            [
                "public_data_source",
                "k_business_lane",
                "k_priority_band",
                "strategic_demand_signal",
                "title",
                "buyer",
                "country",
                "region_city",
                "deadline",
                "category",
                "technical_trade_relevance_score",
                "pro_builder_relevance_score",
                "sales_territory",
                "territory_owner",
                "recommended_k_action",
                "source_url",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={"source_url": st.column_config.LinkColumn("Source")},
    )
    if today_df.empty:
        st.caption("No notices in the local database were published today, so the latest scored notices are shown.")


def show_pipeline(df: pd.DataFrame) -> None:
    st.title("Category Pipeline")
    show_page_guide("Category pipeline")
    if df.empty:
        st.info("Run ingestion to build the category pipeline.")
        return
    working = df.copy()
    working["best_score"] = working[["technical_trade_relevance_score", "pro_builder_relevance_score"]].max(axis=1)
    working["band"] = working["best_score"].apply(score_band)
    summary = (
        working.groupby(["public_data_source", "category", "k_business_lane", "band"], as_index=False)
        .agg(notices=("title", "count"), avg_best_score=("best_score", "mean"))
        .sort_values(["avg_best_score", "notices"], ascending=False)
    )
    st.dataframe(summary, hide_index=True, width="stretch")

    category_counts = working.groupby("category")["title"].count().sort_values(ascending=False)
    st.bar_chart(category_counts)

    st.subheader("Score Components Are Deterministic")
    st.write(
        "Scores combine CPV match, keyword match, deadline urgency, location availability, "
        "and source text confidence. Evidence and uncertainty fields show which source data drove each result."
    )


def show_detail(df: pd.DataFrame, awards: pd.DataFrame) -> None:
    st.title("Notice Detail / Sales Brief")
    show_page_guide("Notice detail / sales brief")
    if df.empty:
        st.info("Run ingestion first.")
        return
    choices = {f"{row['title'][:90]} | {row['buyer']} | {row['publication_number']}": i for i, row in df.iterrows()}
    selected_label = st.selectbox("Notice", list(choices.keys()))
    row = df.iloc[choices[selected_label]]

    cols = st.columns([2, 1])
    with cols[0]:
        st.subheader(row["title"])
        st.write(row["sales_briefing"])
    with cols[1]:
        st.metric("Technical trade", f"{row['technical_trade_relevance_score']:.0f}")
        st.metric("Pro builder", f"{row['pro_builder_relevance_score']:.0f}")
        st.write(f"**Source:** {row['public_data_source']}")
        st.write(f"**K lane:** {row['k_business_lane']}")
        st.write(f"**Demand signal:** {row['strategic_demand_signal']}")
        st.write(f"**Category:** {row['category']}")
        st.write(f"**Buyer:** {row['buyer']}")
        st.write(f"**Deadline:** {row['deadline'] or 'Not returned'}")
        st.write(f"**Territory:** {row['sales_territory'] or 'No configured mapping'}")
        st.write(f"**Owner:** {row['territory_owner'] or 'Not mapped'}")
        st.write(f"**LLM:** {row['llm_enrichment_status']}")
        st.link_button("Open source notice", row["source_url"], width="stretch")

    st.subheader("Evidence")
    for item in parse_list(row["evidence"]):
        st.write(f"- {item}")

    st.subheader("Uncertainties")
    uncertainties = parse_list(row["uncertainties"])
    if uncertainties:
        for item in uncertainties:
            st.write(f"- {item}")
    else:
        st.write("No major source-field uncertainties detected.")

    with st.expander("Raw description"):
        st.write(row["raw_description"] or "No description returned.")

    with st.expander("Document and source links"):
        links = parse_list(row["document_links"])
        if links:
            for link in links:
                st.markdown(f"- [{link}]({link})")
        else:
            st.write("No document URLs returned by source fields.")

    with st.expander("Action pack for sales user", expanded=True):
        st.code(build_action_pack(row, awards), language="markdown")
        outputs = build_ready_outputs(row, awards)
        source_payload = {
            "title": row.get("title", ""),
            "buyer": row.get("buyer", ""),
            "source": row.get("public_data_source", ""),
            "deadline": row.get("deadline", ""),
            "category": row.get("category", ""),
            "k_business_lane": row.get("k_business_lane", ""),
            "strategic_demand_signal": row.get("strategic_demand_signal", ""),
            "source_url": row.get("source_url", ""),
        }
        polished_outputs = maybe_polish_action_outputs(source_payload, outputs)
        for label, text in polished_outputs.items():
            st.text_area(label, value=text, height=120 if label != "Qualification checklist" else 180)

    with st.expander("Ask this tender", expanded=True):
        question = st.selectbox("Question", QUESTIONS)
        st.write(answer_question(row, awards, question))


def show_reliability(db_path: Path, df: pd.DataFrame) -> None:
    st.title("Data Reliability")
    show_page_guide("Data reliability")
    st.write(
        "TenderSignal uses the public TED Search API and stores the raw notice payload next to normalized fields. "
        "If the API fails, ingestion records a failed run and the app does not fabricate replacement notices."
    )
    runs = [dict(row) for row in load_ingestion_runs(db_path)]
    st.subheader("Ingestion Runs")
    if runs:
        st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
    else:
        st.info("No ingestion runs recorded yet.")

    st.subheader("Field Completeness")
    if df.empty:
        st.info("No notices available for completeness checks.")
        return
    completeness = []
    for column in [
        "title",
        "buyer",
        "country",
        "region_city",
        "deadline",
        "source_url",
        "cpv_codes",
        "document_links",
        "raw_description",
        "sales_territory",
    ]:
        present = df[column].fillna("").astype(str).str.len().gt(0).mean() * 100
        completeness.append({"field": column, "present_percent": round(present, 1)})
    st.dataframe(pd.DataFrame(completeness), hide_index=True, width="stretch")

    st.subheader("Known Limitations")
    st.write("- Location can be a NUTS code rather than a city.")
    st.write("- Description language depends on what TED returns for the notice.")
    st.write("- The first MVP uses deterministic CPV and keyword rules only; optional LLM enrichment is isolated and disabled.")
    st.write("- K business lane and demand signal fields are derived from public notice fields and deterministic scores.")
    st.write("- Scores are triage signals, not bid/no-bid decisions.")


def show_export(db_path: Path, df: pd.DataFrame) -> None:
    st.title("Export")
    show_page_guide("Export")
    if df.empty:
        st.info("Run ingestion before exporting.")
        return
    if st.button("Create CSV export", type="primary"):
        path = export_csv(db_path)
        st.success(f"CSV created: {path}")
        refresh_data()

    csv_data = df[EXPORT_COLUMNS].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download current scored opportunities",
        csv_data,
        file_name="tendersignal_opportunities.csv",
        mime="text/csv",
    )
    st.dataframe(df[EXPORT_COLUMNS], hide_index=True, width="stretch")


def main() -> None:
    db_path = DEFAULT_DB_PATH
    init_db(db_path)
    seed_messages: list[str] = []
    if not load_opportunities(db_path):
        with st.spinner("Loading bundled real public procurement data..."):
            seed_messages = seed_database_from_public_cache(db_path)
    page = show_navigation()
    source_filter = show_ingest_controls(db_path)
    db_version = db_path.stat().st_mtime_ns if db_path.exists() else 0
    df = add_business_columns(cached_dataframe(str(db_path), db_version))
    df = apply_source_filter(df, source_filter)
    df = apply_publication_date_filter(df)
    awards = cached_awards_dataframe(str(db_path), db_version)
    if seed_messages:
        with st.sidebar.expander("Startup data load", expanded=False):
            for message in seed_messages:
                st.write(f"- {message}")

    if page == "K business radar":
        show_business_radar(df)
    elif page == "Opportunity map":
        show_opportunity_map(df, awards)
    elif page == "Award & competitor intelligence":
        show_award_intelligence(awards)
    elif page == "Buyer 360":
        show_buyer_360(df, awards)
    elif page == "Today's opportunities":
        show_today(df)
    elif page == "Category pipeline":
        show_pipeline(df)
    elif page == "Notice detail / sales brief":
        show_detail(df, awards)
    elif page == "Data reliability":
        show_reliability(db_path, df)
    elif page == "Export":
        show_export(db_path, df)


if __name__ == "__main__":
    main()
