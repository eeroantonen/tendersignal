from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from tendersignal.models import Notice, ScoredOpportunity


@dataclass(frozen=True)
class CategoryRule:
    name: str
    cpv_prefixes: tuple[str, ...]
    keywords: tuple[str, ...]


CATEGORY_RULES = (
    CategoryRule(
        "Electrical, telecom and lighting",
        ("31", "312", "313", "315", "316", "4531", "453143", "642", "324"),
        (
            "electrical",
            "electric",
            "lighting",
            "cable",
            "fibre",
            "fiber",
            "telecom",
            "low voltage",
            "sähkö",
            "valaistus",
            "kaapeli",
            "fibernät",
            "broadband",
            "verkko",
        ),
    ),
    CategoryRule(
        "HVAC, plumbing and water systems",
        ("397", "421", "425", "4416", "4533", "452321", "452324", "507"),
        (
            "hvac",
            "heating",
            "cooling",
            "ventilation",
            "plumbing",
            "pipe",
            "pump",
            "water",
            "sewer",
            "lvi",
            "lämmitys",
            "ilmanvaihto",
            "vesi",
            "viemäri",
            "värme",
            "ventilation",
        ),
    ),
    CategoryRule(
        "Building materials and structural works",
        ("44", "441", "442", "443", "452", "453", "454", "455"),
        (
            "construction",
            "building",
            "renovation",
            "repair",
            "concrete",
            "timber",
            "roof",
            "window",
            "door",
            "rakennus",
            "korjaus",
            "betoni",
            "puu",
            "katto",
            "bygg",
            "renovering",
        ),
    ),
    CategoryRule(
        "Civil works and site infrastructure",
        ("451", "4523", "4522", "45233", "45231"),
        (
            "road",
            "street",
            "earthwork",
            "excavation",
            "infrastructure",
            "asphalt",
            "site",
            "tie",
            "katu",
            "maanrakennus",
            "infra",
            "väg",
            "gata",
        ),
    ),
    CategoryRule(
        "Tools, machinery and site equipment",
        ("426", "433", "438", "445", "455"),
        (
            "tool",
            "machinery",
            "equipment",
            "drill",
            "saw",
            "workwear",
            "safety",
            "työkalu",
            "kone",
            "laite",
            "skydd",
        ),
    ),
)

TECHNICAL_PREFIXES = ("31", "312", "313", "315", "316", "324", "397", "421", "425", "4416", "45231", "45232", "4531", "4533", "507", "642")
PRO_BUILDER_PREFIXES = ("43", "44", "441", "442", "443", "445", "451", "452", "453", "454", "455")

TECHNICAL_KEYWORDS = tuple(sorted({kw for rule in CATEGORY_RULES[:2] for kw in rule.keywords}))
PRO_BUILDER_KEYWORDS = tuple(sorted({kw for rule in CATEGORY_RULES[2:] for kw in rule.keywords}))


def classify_notice(notice: Notice, today: date | None = None) -> ScoredOpportunity:
    today = today or date.today()
    category, category_evidence = choose_category(notice)
    tech_score, tech_evidence, tech_uncertainties = score_notice(notice, TECHNICAL_PREFIXES, TECHNICAL_KEYWORDS, today, "technical trade")
    pro_score, pro_evidence, pro_uncertainties = score_notice(notice, PRO_BUILDER_PREFIXES, PRO_BUILDER_KEYWORDS, today, "pro builder")

    evidence = dedupe(category_evidence + tech_evidence + pro_evidence)
    uncertainties = dedupe(tech_uncertainties + pro_uncertainties + base_uncertainties(notice))
    action = recommend_action(tech_score, pro_score, notice.deadline)

    return ScoredOpportunity(
        notice=notice,
        category=category,
        technical_trade_relevance_score=tech_score,
        pro_builder_relevance_score=pro_score,
        recommended_sales_action=action,
        evidence=evidence,
        uncertainties=uncertainties,
    )


def choose_category(notice: Notice) -> tuple[str, list[str]]:
    text = searchable_text(notice)
    best_name = "Other building or technical trade"
    best_points = 0
    evidence: list[str] = []
    for rule in CATEGORY_RULES:
        cpv_hits = [code for code in notice.cpv_codes if matches_prefix(code, rule.cpv_prefixes)]
        keyword_hits = find_keywords(text, rule.keywords)
        points = len(cpv_hits) * 3 + len(keyword_hits)
        if points > best_points:
            best_name = rule.name
            best_points = points
            evidence = []
            if cpv_hits:
                evidence.append(f"Category from CPV matches: {', '.join(cpv_hits[:6])}")
            if keyword_hits:
                evidence.append(f"Category keywords found in title/description: {', '.join(keyword_hits[:6])}")
    if not evidence:
        evidence.append("Category fallback: no stronger CPV or keyword category matched.")
    return best_name, evidence


def score_notice(
    notice: Notice,
    cpv_prefixes: tuple[str, ...],
    keywords: tuple[str, ...],
    today: date,
    label: str,
) -> tuple[float, list[str], list[str]]:
    evidence: list[str] = []
    uncertainties: list[str] = []
    text = searchable_text(notice)

    cpv_hits = [code for code in notice.cpv_codes if matches_prefix(code, cpv_prefixes)]
    cpv_component = 40 if cpv_hits else 0
    if cpv_hits:
        evidence.append(f"{label} CPV component 40/40 from matching CPV codes: {', '.join(cpv_hits[:8])}")
    else:
        uncertainties.append(f"No {label} CPV prefix match in classification-cpv.")

    keyword_hits = find_keywords(text, keywords)
    keyword_component = min(25, len(keyword_hits) * 5)
    if keyword_hits:
        evidence.append(f"{label} keyword component {keyword_component}/25 from: {', '.join(keyword_hits[:8])}")
    else:
        uncertainties.append(f"No {label} keywords found in title or description.")

    urgency_component = deadline_component(notice.deadline, today)
    if notice.deadline:
        evidence.append(f"Deadline urgency component {urgency_component}/15 from deadline field: {notice.deadline}")
    else:
        uncertainties.append("No tender deadline field returned by source.")

    location_component = 10 if notice.region_city else 0
    if notice.region_city:
        evidence.append(f"Location component 10/10 from place-of-performance: {notice.region_city}")
    else:
        uncertainties.append("No place-of-performance field returned by source.")

    confidence_component = text_confidence_component(notice)
    evidence.append(f"Text confidence component {confidence_component}/10 from title/description availability.")

    score = min(100, cpv_component + keyword_component + urgency_component + location_component + confidence_component)
    return float(score), evidence, uncertainties


def recommend_action(technical_score: float, pro_score: float, deadline: str) -> str:
    days = days_until(deadline)
    max_score = max(technical_score, pro_score)
    audience = "technical trade team" if technical_score >= pro_score else "pro builder sales team"
    if max_score >= 75 and days is not None and days <= 14:
        return f"Prioritize today: route to {audience}, validate documents, and contact buyer/procurement portal quickly."
    if max_score >= 65:
        return f"Qualify this week with {audience}; check lots, delivery geography, and framework fit."
    if max_score >= 45:
        return f"Monitor and enrich manually; possible fit but evidence is moderate."
    return "Low deterministic fit; keep for pipeline awareness unless a local sales team recognizes the buyer."


def base_uncertainties(notice: Notice) -> list[str]:
    uncertainties: list[str] = []
    if not notice.raw_description:
        uncertainties.append("Description is missing, so briefing uses title and CPV only.")
    if notice.region_city and re.fullmatch(r"([A-Z]{2,3}[A-Z0-9]{0,3},?\\s*)+", notice.region_city):
        uncertainties.append("Location is a NUTS/country code from TED, not a confirmed city name.")
    return uncertainties


def searchable_text(notice: Notice) -> str:
    return f"{notice.title}\n{notice.raw_description}".lower()


def matches_prefix(code: str, prefixes: tuple[str, ...]) -> bool:
    compact = re.sub(r"\D", "", code)
    return any(compact.startswith(prefix) for prefix in prefixes)


def find_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    hits = []
    for keyword in keywords:
        pattern = r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)"
        if re.search(pattern, text):
            hits.append(keyword)
    return hits


def deadline_component(deadline: str, today: date) -> int:
    days = days_until(deadline, today)
    if days is None or days < 0:
        return 0
    if days <= 14:
        return 15
    if days <= 30:
        return 12
    if days <= 60:
        return 8
    return 4


def days_until(deadline: str, today: date | None = None) -> int | None:
    if not deadline:
        return None
    today = today or date.today()
    try:
        normalized = deadline[:10]
        return (datetime.strptime(normalized, "%Y-%m-%d").date() - today).days
    except ValueError:
        return None


def text_confidence_component(notice: Notice) -> int:
    if len(notice.raw_description) >= 180 and notice.title:
        return 10
    if notice.raw_description or notice.title:
        return 6
    return 0


def dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
