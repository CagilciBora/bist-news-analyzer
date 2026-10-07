"""Seed / update the `stocks` table from config/stocks.yaml (idempotent).

Usage:
    uv run python scripts/seed_stocks.py [--file path/to/stocks.yaml]
"""

import argparse
from pathlib import Path

from app.core.db import SessionLocal
from app.services.stock_seed import DEFAULT_STOCKS_FILE, load_stock_seeds, upsert_stocks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_STOCKS_FILE)
    args = parser.parse_args()

    seeds = load_stock_seeds(args.file)
    with SessionLocal.begin() as session:
        result = upsert_stocks(session, seeds)

    print(f"Loaded {len(seeds)} stocks from {args.file}")
    print(f"  inserted: {len(result.inserted)} {result.inserted or ''}")
    print(f"  updated:  {len(result.updated)} {result.updated or ''}")


if __name__ == "__main__":
    main()
