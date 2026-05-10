from __future__ import annotations

import re
from typing import Any

from tendersignal.text import first_text


CITY_CENTROIDS: dict[str, dict[str, float | str]] = {
    "Aalborg": {"country": "DNK", "lat": 57.0488, "lon": 9.9217},
    "Aarhus": {"country": "DNK", "lat": 56.1629, "lon": 10.2039},
    "Alta": {"country": "NOR", "lat": 69.9689, "lon": 23.2716},
    "Bergen": {"country": "NOR", "lat": 60.3913, "lon": 5.3221},
    "Copenhagen": {"country": "DNK", "lat": 55.6761, "lon": 12.5683},
    "Espoo": {"country": "FIN", "lat": 60.2055, "lon": 24.6559},
    "Eurajoki": {"country": "FIN", "lat": 61.2000, "lon": 21.7333},
    "Gislaved": {"country": "SWE", "lat": 57.3044, "lon": 13.5408},
    "Gothenburg": {"country": "SWE", "lat": 57.7089, "lon": 11.9746},
    "Halmstad": {"country": "SWE", "lat": 56.6745, "lon": 12.8578},
    "Helsinki": {"country": "FIN", "lat": 60.1699, "lon": 24.9384},
    "Herning": {"country": "DNK", "lat": 56.1393, "lon": 8.9738},
    "Joensuu": {"country": "FIN", "lat": 62.6010, "lon": 29.7636},
    "Jyväskylä": {"country": "FIN", "lat": 62.2426, "lon": 25.7473},
    "Kohtla-Järve": {"country": "EST", "lat": 59.3986, "lon": 27.2731},
    "Kotka": {"country": "FIN", "lat": 60.4664, "lon": 26.9458},
    "Kuopio": {"country": "FIN", "lat": 62.8924, "lon": 27.6770},
    "Lahti": {"country": "FIN", "lat": 60.9827, "lon": 25.6615},
    "Lappeenranta": {"country": "FIN", "lat": 61.0587, "lon": 28.1887},
    "Lund": {"country": "SWE", "lat": 55.7047, "lon": 13.1910},
    "Lyngby": {"country": "DNK", "lat": 55.7704, "lon": 12.5038},
    "Malmö": {"country": "SWE", "lat": 55.6050, "lon": 13.0038},
    "Mikkeli": {"country": "FIN", "lat": 61.6886, "lon": 27.2723},
    "Nyköping": {"country": "SWE", "lat": 58.7528, "lon": 17.0079},
    "Oulu": {"country": "FIN", "lat": 65.0121, "lon": 25.4651},
    "Oslo": {"country": "NOR", "lat": 59.9139, "lon": 10.7522},
    "Pori": {"country": "FIN", "lat": 61.4851, "lon": 21.7972},
    "Porvoo": {"country": "FIN", "lat": 60.3923, "lon": 25.6651},
    "Rovaniemi": {"country": "FIN", "lat": 66.5039, "lon": 25.7294},
    "Salo": {"country": "FIN", "lat": 60.3831, "lon": 23.1331},
    "Seinäjoki": {"country": "FIN", "lat": 62.7903, "lon": 22.8403},
    "Sillamäe": {"country": "EST", "lat": 59.3960, "lon": 27.7636},
    "Stockholm": {"country": "SWE", "lat": 59.3293, "lon": 18.0686},
    "Tallinn": {"country": "EST", "lat": 59.4370, "lon": 24.7536},
    "Tampere": {"country": "FIN", "lat": 61.4978, "lon": 23.7610},
    "Tartu": {"country": "EST", "lat": 58.3776, "lon": 26.7290},
    "Turku": {"country": "FIN", "lat": 60.4518, "lon": 22.2666},
    "Vaasa": {"country": "FIN", "lat": 63.0951, "lon": 21.6165},
    "Vantaa": {"country": "FIN", "lat": 60.2934, "lon": 25.0378},
}


CITY_ALIASES = {
    "Göteborg": "Gothenburg",
    "København": "Copenhagen",
    "Kobenhavn": "Copenhagen",
    "Köpenhamn": "Copenhagen",
}

CITY_LOOKUP = {city.lower(): city for city in CITY_CENTROIDS}
CITY_LOOKUP.update({alias.lower(): canonical for alias, canonical in CITY_ALIASES.items()})
CITY_PATTERN = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(name) for name in sorted(CITY_LOOKUP, key=len, reverse=True))
    + r")(?!\w)",
    flags=re.IGNORECASE,
)


def extract_city_from_notice_row(row: Any) -> tuple[str, str]:
    short_fields = [
        row_get(row, "title"),
        row_get(row, "buyer"),
        row_get(row, "region_city"),
    ]
    city, evidence = city_from_text(" | ".join(str(value or "") for value in short_fields))
    if city:
        return city, evidence

    source_name = str(row_get(row, "source_name") or row_get(row, "public_data_source") or "")
    if "Hilma" not in source_name and "Hankintailmoitus" not in source_name:
        return "", ""

    raw = row_raw(row, "raw_notice")
    address = first_text(raw.get("organisationAddress"))
    city = city_from_address(address)
    if city:
        return city, f"organisationAddress: {address}"

    fields = [
        first_text(raw.get("titleFi")),
        first_text(raw.get("titleEn")),
        first_text(raw.get("organisationNameFi")),
        first_text(raw.get("organisationNameEn")),
    ]
    return city_from_text(" | ".join(str(value or "") for value in fields))


def extract_city_from_award_row(row: Any) -> tuple[str, str]:
    raw = row_raw(row, "raw_award")
    address = first_text(raw.get("organisationAddress"))
    city = city_from_address(address)
    if city:
        return city, f"organisationAddress: {address}"
    fields = [
        row_get(row, "title"),
        row_get(row, "buyer"),
        row_get(row, "region_city"),
        first_text(raw.get("titleFi")),
        first_text(raw.get("titleEn")),
        first_text(raw.get("organisationNameFi")),
        first_text(raw.get("organisationNameEn")),
    ]
    return city_from_text(" | ".join(str(value or "") for value in fields))


def city_from_address(address: str) -> str:
    normalized = " ".join(str(address or "").split())
    if not normalized:
        return ""
    match = re.search(r"\b\d{5}\s+([A-Za-zÅÄÖåäöÉéØøÆæÜü\-]+(?:\s+[A-Za-zÅÄÖåäöÉéØøÆæÜü\-]+)?)\s+(?:FIN|SWE|NOR|DNK|EST)\b", normalized)
    if match:
        return canonical_city(match.group(1))
    city, _ = city_from_text(normalized)
    return city


def city_from_text(text: str) -> tuple[str, str]:
    normalized = str(text or "")
    match = CITY_PATTERN.search(normalized)
    if match:
        source_value = match.group(1)
        return CITY_LOOKUP[source_value.lower()], f"matched source text city: {source_value}"
    return "", ""


def canonical_city(value: str) -> str:
    cleaned = " ".join(str(value or "").replace(",", " ").split())
    if not cleaned:
        return ""
    for alias, canonical in CITY_ALIASES.items():
        if cleaned.lower() == alias.lower():
            return canonical
    for city in CITY_CENTROIDS:
        if cleaned.lower() == city.lower():
            return city
    return ""


def row_get(row: Any, key: str) -> Any:
    if hasattr(row, "get"):
        return row.get(key)
    return getattr(row, key, "")


def row_raw(row: Any, key: str) -> dict[str, Any]:
    import json

    value = row_get(row, key)
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
