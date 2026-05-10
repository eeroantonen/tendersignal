from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from tendersignal.config import TERRITORY_MAPPING_PATH
from tendersignal.models import ScoredOpportunity


@dataclass(frozen=True)
class TerritoryRule:
    buyer_contains: str
    country: str
    region_contains: str
    category_contains: str
    cpv_prefix: str
    account_segment: str
    sales_territory: str
    territory_owner: str


def load_rules(path: Path = TERRITORY_MAPPING_PATH) -> list[TerritoryRule]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [TerritoryRule(**normalize_row(row)) for row in csv.DictReader(handle)]


def apply_territory_mapping(
    opportunity: ScoredOpportunity,
    rules: list[TerritoryRule] | None = None,
) -> ScoredOpportunity:
    rules = rules if rules is not None else load_rules()
    for rule in rules:
        if matches_rule(opportunity, rule):
            opportunity.account_segment = rule.account_segment
            opportunity.sales_territory = rule.sales_territory
            opportunity.territory_owner = rule.territory_owner
            opportunity.mapping_evidence = build_evidence(rule)
            return opportunity
    opportunity.mapping_evidence = "No configured territory/account rule matched. Add real K Group/Onninen rules in config/sales_territory_mapping.csv."
    return opportunity


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "buyer_contains": row.get("buyer_contains", "").strip(),
        "country": row.get("country", "").strip().upper(),
        "region_contains": row.get("region_contains", "").strip(),
        "category_contains": row.get("category_contains", "").strip(),
        "cpv_prefix": row.get("cpv_prefix", "").strip(),
        "account_segment": row.get("account_segment", "").strip(),
        "sales_territory": row.get("sales_territory", "").strip(),
        "territory_owner": row.get("territory_owner", "").strip(),
    }


def matches_rule(opportunity: ScoredOpportunity, rule: TerritoryRule) -> bool:
    notice = opportunity.notice
    checks = []
    if rule.buyer_contains:
        checks.append(rule.buyer_contains.lower() in notice.buyer.lower())
    if rule.country:
        checks.append(rule.country == notice.country.upper())
    if rule.region_contains:
        checks.append(rule.region_contains.lower() in notice.region_city.lower())
    if rule.category_contains:
        checks.append(rule.category_contains.lower() in opportunity.category.lower())
    if rule.cpv_prefix:
        checks.append(any(code.startswith(rule.cpv_prefix) for code in notice.cpv_codes))
    return bool(checks) and all(checks)


def build_evidence(rule: TerritoryRule) -> str:
    fields = []
    for name in ("buyer_contains", "country", "region_contains", "category_contains", "cpv_prefix"):
        value = getattr(rule, name)
        if value:
            fields.append(f"{name}={value}")
    return "Matched configured rule: " + ", ".join(fields)
