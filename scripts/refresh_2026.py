#!/usr/bin/env python3
from __future__ import annotations

from datetime import date

from tendersignal.awards import run_hilma_award_ingestion
from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.pipeline import run_hilma_ingestion_for_period, run_ted_ingestion_for_period
from tendersignal.winner_leads import run_hilma_winner_lead_ingestion


def main() -> None:
    start = date(2026, 1, 1)
    end = date(2027, 1, 1)
    print("Refreshing TED 2026 notices...")
    ted_count = run_ted_ingestion_for_period(DEFAULT_DB_PATH, start, end, limit=10000)
    print(f"TED notices: {ted_count}")
    print("Refreshing Hilma 2026 notices...")
    hilma_count = run_hilma_ingestion_for_period(DEFAULT_DB_PATH, start, end, limit=10000, include_expired=True)
    print(f"Hilma notices: {hilma_count}")
    print("Refreshing Hilma award intelligence...")
    award_count = run_hilma_award_ingestion(DEFAULT_DB_PATH, days_back=1460)
    print(f"Award notices: {award_count}")
    print("Refreshing Hilma winner lead radar...")
    winner_count = run_hilma_winner_lead_ingestion(DEFAULT_DB_PATH, days_back=1460)
    print(f"Winner leads: {winner_count}")


if __name__ == "__main__":
    main()
