#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from tendersignal.awards import run_hilma_award_ingestion
from tendersignal.config import DEFAULT_DB_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest public Hilma award notices for K Group and competitor intelligence.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--days-back", type=int, default=1460)
    parser.add_argument("--use-cache", action="store_true")
    args = parser.parse_args()
    count = run_hilma_award_ingestion(args.db, days_back=args.days_back, use_cache=args.use_cache)
    print(f"Ingested {count} real Hilma award notices into {args.db}")


if __name__ == "__main__":
    main()
