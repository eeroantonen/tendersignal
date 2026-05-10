from __future__ import annotations

from datetime import date

from tendersignal.classifier import classify_notice
from tendersignal.models import Notice


def make_notice(**overrides):
    values = {
        "publication_number": "1-2026",
        "title": "Fibre network electrical cabling works",
        "buyer": "Example public buyer",
        "country": "SWE",
        "region_city": "SE224",
        "deadline": "2026-06-01+02:00",
        "source_url": "https://ted.europa.eu/en/notice/-/detail/1-2026",
        "cpv_codes": ["45314300", "45000000"],
        "document_links": ["https://ted.europa.eu/en/notice/1-2026/pdf"],
        "raw_description": "The notice concerns fibre network infrastructure, cabling and building works.",
        "publication_date": "2026-05-04+02:00",
        "notice_type": "cn-standard",
        "source_name": "TED Search API",
        "raw_notice": {},
    }
    values.update(overrides)
    return Notice(**values)


def test_classifier_scores_technical_notice_transparently():
    opportunity = classify_notice(make_notice(), today=date(2026, 5, 8))

    assert opportunity.category == "Electrical, telecom and lighting"
    assert opportunity.technical_trade_relevance_score >= 75
    assert "CPV" in " ".join(opportunity.evidence)
    assert opportunity.recommended_sales_action


def test_missing_source_fields_create_uncertainties():
    opportunity = classify_notice(
        make_notice(cpv_codes=[], raw_description="", region_city="", deadline=""),
        today=date(2026, 5, 8),
    )

    assert opportunity.technical_trade_relevance_score < 75
    assert any("No tender deadline" in item for item in opportunity.uncertainties)
    assert any("Description is missing" in item for item in opportunity.uncertainties)
