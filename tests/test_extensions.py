from __future__ import annotations

import pytest

from tendersignal.sources.hilma import HilmaApiConfigurationError, HilmaClient, build_hilma_notice_url
from tendersignal.sources.ted import normalize_publication_date
from tendersignal.geo import city_from_address, extract_city_from_notice_row


def test_hilma_client_fails_clearly_without_subscription_key():
    client = HilmaClient(subscription_key="")

    with pytest.raises(HilmaApiConfigurationError) as exc:
        client.search_notices({"search": ""})

    assert "HILMA_AVP_SUBSCRIPTION_KEY" in str(exc.value)
    assert "no Hilma notices were fabricated" in str(exc.value)


def test_hilma_client_fails_clearly_without_search_endpoint():
    client = HilmaClient(subscription_key="test-key", search_endpoint="")

    with pytest.raises(HilmaApiConfigurationError) as exc:
        client.search_notices({"search": "*", "top": 1})

    assert "HILMA_AVP_SEARCH_ENDPOINT" in str(exc.value)
    assert "No Hilma notices were fabricated" in str(exc.value)


def test_ted_publication_date_normalizes_timezone_suffix():
    assert normalize_publication_date(["2026-05-08+02:00"]) == "2026-05-08"


def test_city_from_hilma_address_is_source_grounded():
    assert city_from_address("PL 913 00101 Helsinki FIN") == "Helsinki"


def test_city_from_ted_title_is_source_grounded():
    row = {
        "title": "Finland – Construction work – LVV-työt Rovaniemi",
        "buyer": "Rovaniemen kaupunki",
        "region_city": "FI1D7, FIN",
        "raw_description": "",
        "raw_notice": "{}",
    }

    city, evidence = extract_city_from_notice_row(row)

    assert city == "Rovaniemi"
    assert "source text city" in evidence


def test_hilma_eforms_notice_url_uses_public_procedure_route():
    url = build_hilma_notice_url(
        {
            "id": "EF-48640",
            "isEForms": True,
            "noticeId": 48640,
            "procedureId": 32400,
            "noticeNumber": "2026-048640",
        }
    )

    assert url == "https://www.hankintailmoitukset.fi/fi/public/procedure/32400/enotice/48640"


def test_hilma_old_notice_url_uses_project_and_notice_route():
    url = build_hilma_notice_url(
        {
            "isEForms": False,
            "noticeId": 123,
            "oldProcurementProjectId": 456,
        }
    )

    assert url == "https://www.hankintailmoitukset.fi/fi/public/procurement/456/notice/123"
