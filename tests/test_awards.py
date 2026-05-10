from __future__ import annotations

from tendersignal.awards import normalize_award


def test_normalize_award_keeps_only_configured_winner_matches():
    rows = normalize_award(
        {
            "noticeNumber": "2026-001",
            "noticeId": 1,
            "titleFi": "LVI-tarvikkeet",
            "organisationNameFi": "Test buyer",
            "datePublished": "2026-01-01T00:00:00Z",
            "type": "29",
            "winnerOrganisations": "Onninen Oy (1071207-9)//Dahl Suomi Oy (0992466-4)",
            "noticeResultTotalAmount": 1000.0,
            "noticeResultTotalAmountCurrency": "EUR",
            "cpvCodes": "44100000",
        }
    )

    assert {row["match_group"] for row in rows} == {"K Group", "Competitor"}
    assert {row["matched_supplier"] for row in rows} == {"Onninen Oy", "Dahl Suomi Oy"}


def test_normalize_award_drops_unmatched_search_noise():
    rows = normalize_award(
        {
            "noticeNumber": "2026-002",
            "noticeId": 2,
            "titleFi": "Contains Onninen in text but no winner",
            "organisationNameFi": "Test buyer",
            "winnerOrganisations": "",
        }
    )

    assert rows == []


def test_normalize_award_splits_concatenated_cpv_codes():
    rows = normalize_award(
        {
            "noticeNumber": "2026-003",
            "noticeId": 3,
            "titleFi": "Huolto",
            "organisationNameFi": "Test buyer",
            "winnerOrganisations": "Onninen Oy (1071207-9)",
            "cpvCodes": "5070000050710000",
        }
    )

    assert rows[0]["cpv_codes"] == '["50700000", "50710000"]'
