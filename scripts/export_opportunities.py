#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from tendersignal.config import DEFAULT_DB_PATH
from tendersignal.export import export_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Export scored TenderSignal opportunities to CSV.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    path = export_csv(args.db)
    print(f"Exported opportunities to {path}")


if __name__ == "__main__":
    main()
