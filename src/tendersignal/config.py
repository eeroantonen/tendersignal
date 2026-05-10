from __future__ import annotations

from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
EXPORT_DIR = DATA_DIR / "exports"
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_DB_PATH = DATA_DIR / "tendersignal.sqlite"
TERRITORY_MAPPING_PATH = CONFIG_DIR / "sales_territory_mapping.csv"

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_NOTICE_URL = "https://ted.europa.eu/en/notice/-/detail/{publication_number}"
HILMA_DEVELOPER_PORTAL_URL = "https://hns-hilma-prod-apim.developer.azure-api.net/"
HILMA_AVP_BASE_URL = os.environ.get("HILMA_AVP_BASE_URL", "https://api.hankintailmoitukset.fi")
HILMA_AVP_SEARCH_ENDPOINT = os.environ.get("HILMA_AVP_SEARCH_ENDPOINT", "/avp/eformnotices/docs/search")
HILMA_AVP_SUBSCRIPTION_KEY = os.environ.get("HILMA_AVP_SUBSCRIPTION_KEY", "")
TENDERSIGNAL_ENABLE_LLM = os.environ.get("TENDERSIGNAL_ENABLE_LLM", "").lower() in {"1", "true", "yes"}
TENDERSIGNAL_LLM_PROVIDER = os.environ.get("TENDERSIGNAL_LLM_PROVIDER", "none").lower()
TENDERSIGNAL_LLM_MODEL = os.environ.get("TENDERSIGNAL_LLM_MODEL", "gpt-4.1-mini")

DEFAULT_COUNTRIES = ("FIN", "SWE", "EST", "DNK", "NOR")

COMPETITION_NOTICE_TYPES = (
    "cn-standard",
    "cn-social",
    "pin-cfc-standard",
    "pin-cfc-social",
    "qu-sy",
    "subco",
    "cn-desg",
)

TED_FIELDS = [
    "publication-number",
    "notice-title",
    "title-proc",
    "title-lot",
    "buyer-name",
    "buyer-country",
    "place-of-performance",
    "deadline",
    "deadline-receipt-tender-date-lot",
    "classification-cpv",
    "publication-date",
    "notice-type",
    "description-proc",
    "description-lot",
    "document-url-lot",
    "document-url-part",
    "document-restricted-url-lot",
    "document-restricted-url-part",
    "buyer-profile",
    "buyer-internet-address",
    "contract-url",
]

BUILDING_TECH_CPV_QUERY = (
    "classification-cpv = 31* OR "
    "classification-cpv = 316* OR "
    "classification-cpv = 397* OR "
    "classification-cpv = 421* OR "
    "classification-cpv = 425* OR "
    "classification-cpv = 43* OR "
    "classification-cpv = 44* OR "
    "classification-cpv = 45* OR "
    "classification-cpv = 507*"
)
