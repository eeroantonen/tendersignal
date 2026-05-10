#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.pipeline import run_ingestion, run_ted_ingestion_for_period


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest real public tender notices from TED.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--days-back", type=int, default=21)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--year", type=int, help="Ingest notices published in the given year.")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--use-cache", action="store_true", help="Load data/cache/ted_notices_sample.json instead of calling TED.")
    args = parser.parse_args()

    if args.year:
        start = date(args.year, 1, 1)
        end = date(args.year + 1, 1, 1)
        count = run_ted_ingestion_for_period(args.db, start, end, limit=args.limit)
    elif args.start_date:
        end = args.end_date or date.today()
        count = run_ted_ingestion_for_period(args.db, args.start_date, end, limit=args.limit)
    else:
        count = run_ingestion(args.db, days_back=args.days_back, limit=args.limit, use_cache=args.use_cache)
    print(f"Ingested {count} real TED notices into {args.db}")


if __name__ == "__main__":
    main()
