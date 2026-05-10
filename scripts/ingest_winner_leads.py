#!/usr/bin/env python3
from __future__ import annotations

import argparse

from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.winner_leads import run_hilma_winner_lead_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest real Hilma award winners as K Group sales leads.")
    parser.add_argument("--days-back", type=int, default=1460)
    parser.add_argument("--use-cache", action="store_true")
    args = parser.parse_args()
    count = run_hilma_winner_lead_ingestion(DEFAULT_DB_PATH, days_back=args.days_back, use_cache=args.use_cache)
    print(f"Ingested {count} real Hilma winner leads into {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()
